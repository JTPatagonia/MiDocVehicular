import os
import qrcode
import requests
import threading
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

# Clave de API de Resend (la configuraremos en las variables de entorno de Render)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

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

# Función para enviar correos de forma moderna y segura con Resend (evita bloqueos en Render)
def enviar_correo_resend(destinatario, asunto, texto_cuerpo):
    def tarea():
        try:
            headers = {
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "from": "MiDocVehicular <onboarding@resend.dev>", # O tu dominio verificado si lo tienes
                "to": [destinatario],
                "subject": asunto,
                "text": texto_cuerpo
            }
            response = requests.post("https://api.resend.com/emails", json=data, headers=headers)
            print(f"Respuesta Resend: {response.status_code}, {response.text}")
        except Exception as e:
            print(f"Error enviando correo vía Resend: {e}")

    threading.Thread(target=tarea).start()

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
        
        # Enviar correo de bienvenida
        asunto = "🎉 ¡Bienvenido a MiDocVehicular - Cuenta creada con éxito!"
        cuerpo = """¡Hola!

Tu cuenta en MiDocVehicular ha sido creada con éxito.
Ya puedes iniciar sesión para registrar tus vehículos y gestionar tus códigos QR de fiscalización oficiales para Carabineros de Chile.

Atentamente,
El equipo de MiDocVehicular"""
        
        enviar_correo_resend(email, asunto, cuerpo)
        
        flash("¡Cuenta creada con éxito! Revisa tu bandeja de entrada para el correo de bienvenida e inicia sesión.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/eliminar_cuenta", methods=["POST"])
@login_required
def eliminar_cuenta():
    try:
        usuario = current_user
        Chofer.query.filter_by(usuario_id=usuario.id).delete()
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

        # Enviar aviso con el enlace directo al QR mediante Resend
        fiscalizar_link = url_for("fiscalizar", rut=rut, _external=True)
        asunto_qr = "🚗 Tu Código QR de Fiscalización - MiDocVehicular"
        cuerpo_qr = f"""Hola {nombre},

Tus documentos vehiculares han sido registrados con éxito en MiDocVehicular.
Puedes acceder directamente a tu tarjeta de fiscalización y código QR para Carabineros en el siguiente enlace:
{fiscalizar_link}

Atentamente,
Equipo MiDocVehicular"""
        
        enviar_correo_resend(current_user.email, asunto_qr, cuerpo_qr)

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