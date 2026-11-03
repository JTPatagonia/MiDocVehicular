import os
import qrcode
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave_secreta_super_segura")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://usuario:password@localhost:5432/validador_db")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "midocvehicular@gmail.com")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "tu_contraseña_de_aplicacion_google")

class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    choferes = db.relationship("Chofer", backref="propietario", cascade="all, delete-orphan", lazy=True)

class Chofer(db.Model):
    __tablename__ = "choferes"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    rut = db.Column(db.String(20), unique=True, nullable=False)
    patente = db.Column(db.String(10), nullable=False)
    tipo_licencia = db.Column(db.String(100), nullable=False)
    
    venc_licencia = db.Column(db.String(20), nullable=False)
    venc_permiso = db.Column(db.String(20), nullable=False)
    venc_revision = db.Column(db.String(20), nullable=False)
    venc_soap = db.Column(db.String(20), nullable=False)
    
    doc_licencia = db.Column(db.String(255))
    doc_permiso = db.Column(db.String(255))
    doc_revision = db.Column(db.String(255))
    doc_soap = db.Column(db.String(255))
    qr_code = db.Column(db.String(255))

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Error al crear tablas: {e}")

def enviar_correo_qr(destinatario, nombre_chofer, qr_path):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = '🚗 Tu Código QR de Fiscalización - MiDocVehicular'
        msg['From'] = MAIL_USERNAME
        msg['To'] = destinatario

        cuerpo = f"""
        Hola {nombre_chofer},
        
        Tus documentos vehiculares han sido registrados con éxito en MiDocVehicular.
        Adjunto encontrarás tu código QR oficial para el control de Carabineros de Chile.
        
        Atentamente,
        Equipo MiDocVehicular
        """
        msg.attach(MIMEText(cuerpo, 'plain'))

        with open(qr_path, 'rb') as f:
            img_data = f.read()
        
        img = MIMEImage(img_data, name="codigo_qr.png")
        img.add_header('Content-ID', '<qr_code>')
        msg.attach(img)

        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error al enviar correo QR: {e}")
        return False

@app.route("/")
def raiz():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario and check_password_hash(usuario.password, password):
            login_user(usuario)
            return redirect(url_for("index"))
        flash("Correo o contraseña incorrectos.", "danger")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente:
            flash("El correo ya está registrado.", "danger")
            return redirect(url_for("register"))
            
        nuevo_usuario = Usuario(email=email, password=generate_password_hash(password, method='scrypt'))
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        flash("¡Cuenta creada con éxito! Ya puedes iniciar sesión.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# Ruta para eliminar la cuenta actual de forma segura
@app.route("/eliminar_cuenta", methods=["POST"])
@login_required
def eliminar_cuenta():
    try:
        usuario = current_user
        # Eliminar primero los choferes asociados para evitar errores de llave foránea
        Chofer.query.filter_by(usuario_id=usuario.id).delete()
        # Eliminar el usuario
        db.session.delete(usuario)
        db.session.commit()
        logout_user()
        flash("Tu cuenta ha sido eliminada correctamente.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al eliminar la cuenta: {str(e)}", "danger")
    
    return redirect(url_for("login"))

@app.route("/portal")
@login_required
def index():
    return render_template("index.html")

@app.route("/registrar", methods=["POST"])
@login_required
def registrar():
    try:
        nombre = request.form.get("nombre")
        rut = request.form.get("rut")
        patente = request.form.get("patente", "").upper()
        
        licencias_seleccionadas = request.form.getlist("tipo_licencia")
        tipo_licencia = ", ".join(licencias_seleccionadas) if licencias_seleccionadas else "No especificada"
        
        venc_licencia = request.form.get("venc_licencia")
        venc_permiso = request.form.get("venc_permiso")
        venc_revision = request.form.get("venc_revision")
        venc_soap = request.form.get("venc_soap")
        
        def guardar_archivo(input_name):
            file = request.files.get(input_name)
            if file and file.filename != "":
                filename = secure_filename(f"{rut}_{input_name}_{file.filename}")
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)
                return filepath.replace("\\", "/")
            return None

        path_licencia = guardar_archivo("doc_licencia")
        path_permiso = guardar_archivo("doc_permiso")
        path_revision = guardar_archivo("doc_revision")
        path_soap = guardar_archivo("doc_soap")

        chofer = Chofer.query.filter_by(rut=rut).first()
        if not chofer:
            chofer = Chofer(rut=rut, usuario_id=current_user.id)
            db.session.add(chofer)
            
        chofer.nombre = nombre
        chofer.patente = patente
        chofer.tipo_licencia = tipo_licencia
        chofer.venc_licencia = venc_licencia
        chofer.venc_permiso = venc_permiso
        chofer.venc_revision = venc_revision
        chofer.venc_soap = venc_soap
        
        if path_licencia: chofer.doc_licencia = path_licencia
        if path_permiso: chofer.doc_permiso = path_permiso
        if path_revision: chofer.doc_revision = path_revision
        if path_soap: chofer.doc_soap = path_soap
        
        db.session.commit()

        qr_filename = f"qr_{rut.replace('.', '').replace('-', '')}.png"
        qr_path = os.path.join(app.config["UPLOAD_FOLDER"], qr_filename)
        
        qr_url_target = url_for("fiscalizar", rut=rut, _external=True)
        img = qrcode.make(qr_url_target)
        img.save(qr_path)
        
        chofer.qr_code = qr_path.replace("\\", "/")
        db.session.commit()

        enviar_correo_qr(current_user.email, nombre, qr_path)

        qr_web_path = url_for("static", filename=f"uploads/{qr_filename}")
        return render_template("index.html", qr_url=qr_web_path)
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error al registrar: {str(e)}", "danger")
        return redirect(url_for("index"))

@app.route("/fiscalizar/<rut>")
def fiscalizar(rut):
    chofer = Chofer.query.filter_by(rut=rut).first_or_404()
    return render_template("fiscalizar.html", chofer=chofer)

if __name__ == "__main__":
    app.run(debug=True)