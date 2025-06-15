from flask import Flask, redirect, url_for, render_template, session, request, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_dance.contrib.google import make_google_blueprint, google
from datetime import datetime
import os
import pandas as pd
from io import BytesIO
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = "your_secret_key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///grocery.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Configure Google OAuth
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Google OAuth Blueprint
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ],
    redirect_to="dashboard"  # Use `redirect_to` instead of `redirect_url`
)
app.register_blueprint(google_bp, url_prefix="/login")

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship('Item', backref='user')


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Float)
    quantity = db.Column(db.Integer)
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'))


class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    quantity = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    total_price = db.Column(db.Float)
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    item = db.relationship('Item', backref='purchases')


# Routes
@app.route('/')
def index():
    # db.create_all()
    if not google.authorized:
        return redirect(url_for("google.login"))
    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        return "Failed to fetch user info", 500

    user_info = resp.json()
    user = User.query.filter_by(google_id=user_info["id"]).first()
    if not user:
        user = User(
            google_id=user_info["id"],
            name=user_info["name"],
            email=user_info["email"]
        )
        db.session.add(user)
        db.session.commit()
    session['user_id'] = user.id

    return redirect(url_for('dashboard'))  # Default to Home

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    items = Item.query.all()
    purchases = Purchase.query.all()
    customers = [row[0] for row in db.session.query(Purchase.customer_name).distinct()]

    return render_template("home.html", items=items, purchases=purchases, customers=customers)

@app.route('/inventory')
def inventory():
    items = Item.query.all()
    return render_template('inventory.html', items=items)

@app.route('/manage')
def manage():
    return render_template('manage.html')

@app.route('/add_item', methods=['GET', 'POST'])
def add_item():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user_id = session['user_id']

    if request.method == 'POST':
        names = request.form.getlist('item_name[]')
        prices = request.form.getlist('price[]')
        quantities = request.form.getlist('quantity[]')

        for name, price, qty in zip(names, prices, quantities):
            item = Item(name=name, price=float(price), quantity=int(qty), added_by=user_id)
            db.session.add(item)
        db.session.commit()

        return redirect(url_for('inventory'))

@app.route('/edit_item/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    item = Item.query.get_or_404(item_id)
    if request.method == 'POST':
        item.name = request.form['name']
        item.price = float(request.form['price'])
        item.quantity = int(request.form['quantity'])
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('edit_item.html', item=item)

@app.route('/delete_item/<int:item_id>')
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('inventory'))

@app.route('/edit_purchase/<int:purchase_id>', methods=['GET', 'POST'])
def edit_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    items = Item.query.all()
    if request.method == 'POST':
        purchase.customer_name = request.form['customer_name']
        purchase.quantity = float(request.form['quantity'])
        item = Item.query.get(purchase.item_id)
        purchase.total_price = (item.price / item.quantity) * purchase.quantity
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('edit_purchase.html', purchase=purchase, items=items)

@app.route('/delete_purchase/<int:purchase_id>')
def delete_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    db.session.delete(purchase)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/add_purchase', methods=['GET', 'POST'])
def add_purchase():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user_id = session['user_id']
    items = Item.query.all()

    if request.method == 'POST':
        customer_name = request.form['customer_name']
        item_ids = request.form.getlist('item_id[]')
        quantities = request.form.getlist('quantity[]')

        for item_id, qty in zip(item_ids, quantities):
            total_price = Item.query.filter_by(id=item_id).first().price / Item.query.filter_by(id=item_id).first().quantity * float(qty)
            purchase = Purchase(
                customer_name=customer_name,
                item_id=int(item_id),
                quantity=float(qty),
                total_price=total_price,
                added_by=user_id
            )
            db.session.add(purchase)
        db.session.commit()
        return redirect(url_for('dashboard'))

    return render_template('add_purchase.html', items=items)

@app.route('/export-db')
def export_db_to_excel():
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')

    # Dump User table
    user_data = User.query.all()
    user_df = pd.DataFrame([{ "ID": u.id, "Google ID": u.google_id, "Name": u.name, "Email": u.email, "Created At": u.created_at } for u in user_data])
    user_df.to_excel(writer, sheet_name='Users', index=False)

    # Dump Item table
    item_data = Item.query.all()
    item_df = pd.DataFrame([{ "ID": i.id, "Name": i.name, "Price": i.price, "Quantity": i.quantity, "Addedd by": i.added_by } for i in item_data])
    item_df.to_excel(writer, sheet_name='Items', index=False)

    # Dump Purchase table
    purchase_data = Purchase.query.all()
    purchase_df = pd.DataFrame([{ "ID": p.id, "Customer Name": p.customer_name, "Item ID": p.item_id, "Quantity": p.quantity, "Timestamp": p.date, "Total Price":  p.total_price, "Addedd by": p.added_by } for p in purchase_data])
    purchase_df.to_excel(writer, sheet_name='Purchases', index=False)

    writer.close()
    output.seek(0)

    return send_file(output,
                     download_name="grocery_data.xlsx",
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

def sync_to_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("grocery-app-google-credentials.json", scope)
    client = gspread.authorize(creds)

    sheet = client.open_by_key("1Pqid1GeU513LgrgGCHDhCZ4wA9C3POzeizGGn2Ud164")

    def update_sheet(sheet, title, df):
        try:
            if title in [ws.title for ws in sheet.worksheets()]:
                worksheet = sheet.worksheet(title)
            else:
                worksheet = sheet.add_worksheet(title=title, rows="100", cols="20")

            worksheet.clear()
            if not df.empty:
                worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        except Exception as e:
            print(f"Failed to update {title}: {str(e)}")

    users = User.query.all()
    df_users = pd.DataFrame([{ 'ID': u.id, 'Google ID': u.google_id, 'Name': u.name, 'Email': u.email, 'Created At': u.created_at.strftime('%Y-%m-%d %H:%M:%S') } for u in users])
    df_users = df_users.fillna("")
    update_sheet(sheet, "Users", df_users)

    items = Item.query.all()
    df_items = pd.DataFrame([{ 'ID': i.id, 'Name': i.name, 'Price': i.price, 'Quantity': i.quantity, 'Added By': i.added_by } for i in items])
    df_items = df_items.fillna("")
    update_sheet(sheet, "Items", df_items)

    purchases = Purchase.query.all()
    df_purchases = pd.DataFrame([{ 'ID': p.id, 'Customer Name': p.customer_name, 'Item ID': p.item_id, 'Quantity': p.quantity, 'Total Price': p.total_price, 'Created At': p.date.strftime('%Y-%m-%d %H:%M:%S'), 'Added By': p.added_by } for p in purchases])
    df_purchases = df_purchases.fillna("")  # Replace NaN/None with empty string
    update_sheet(sheet, "Purchases", df_purchases)

@app.route("/sync-sheet")
def sync_sheet():
    try:
        sync_to_gsheet()
        flash("✅ Synced to Google Sheet!", "success")
        return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"❌ Sync failed: {str(e)}", "error")
        return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))  # Use the PORT environment variable or default to 5000
    app.run(host="0.0.0.0", port=port,debug=True)

