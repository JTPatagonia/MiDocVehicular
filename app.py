import os
import qrcode
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave_secreta_super_segura")

# Configuración de Base de Datos (PostgreSQL en Render o local)
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://usuario:password@localhost:5432/validador_db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Carpeta de subidas segura
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# Modelo de Base de Datos para Choferes de Chile
class Chofer(db.Model):
    __tablename__ = "choferes"
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    rut = db.Column(db.String(20), unique=True, nullable=False)
    patente = db.Column(db.String(10), nullable=False)
    tipo_licencia = db.Column(db.String(10), nullable=False)
    
    venc_licencia = db.Column(db.String(20), nullable=False)
    venc_permiso = db.Column(db.String(20), nullable=False)
    venc_revision = db.Column(db.String(20), nullable=False)
    venc_soap = db.Column(db.String(20), nullable=False)
    
    doc_licencia = db.Column(db.String(255))
    doc_permiso = db.Column(db.String(255))
    doc_revision = db.Column(db.String(255))
    doc_soap = db.Column(db.String(255))
    
    qr_code = db.Column(db.String(255))

# Crear tablas automáticamente al arrancar
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Error al crear las tablas: {e}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/registrar", methods=["POST"])
def registrar():
    try:
        nombre = request.form.get("nombre")
        rut = request.form.get("rut")
        patente = request.form.get("patente", "").upper()
        tipo_licencia = request.form.get("tipo_licencia")
        
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
                return filepath
            return None

        path_licencia = guardar_archivo("doc_licencia")
        path_permiso = guardar_archivo("doc_permiso")
        path_revision = guardar_archivo("doc_revision")
        path_soap = guardar_archivo("doc_soap")

        chofer = Chofer.query.filter_by(rut=rut).first()
        if not chofer:
            chofer = Chofer(rut=rut)
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

        qr_url = url_for("fiscalizar", rut=rut, _external=True)
        img = qrcode.make(qr_url)
        qr_filename = f"qr_{rut.replace('.', '').replace('-', '')}.png"
        qr_path = os.path.join(app.config["UPLOAD_FOLDER"], qr_filename)
        img.save(qr_path)
        
        chofer.qr_code = qr_path
        db.session.commit()

        flash("¡Documentos registrados y código QR generado con éxito!", "success")
        return redirect(url_for("index"))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error al registrar en la base de datos: {str(e)}", "danger")
        return redirect(url_for("index"))

@app.route("/fiscalizar/<rut>")
def fiscalizar(rut):
    chofer = Chofer.query.filter_by(rut=rut).first_or_404()
    return render_template("fiscalizar.html", chofer=chofer)

if __name__ == "__main__":
    app.run(debug=True)