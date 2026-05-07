import json
import os
import uuid
import re
from functools import wraps

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash  # DICA DO PROFESSOR
from database import get_connection

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")


# O dicionário 'users' foi removido porque agora usamos o Banco de Dados

def login_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return decorated_function


UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- ROTA DE CADASTRO (NOVIDADE) ---
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        password = request.form["password"]

        # Verificação: mínimo 8 caracteres e um caractere especial
        if len(password) < 8 or not re.search(r"[@#$%^&+=!]", password):
            return render_template("cadastro.html", erro="A senha deve ter 8+ caracteres e um símbolo (@#$%^&+=!)")

        # Criptografia da senha antes de salvar
        senha_hash = generate_password_hash(password)

        try:
            conn = get_connection()
            cursor = conn.cursor()
            sql = "INSERT INTO usuario (nome, email, senha) VALUES (%s, %s, %s)"
            cursor.execute(sql, (nome, email, senha_hash))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for("login"))
        except Exception as ex:
            return render_template("cadastro.html", erro="Erro: E-mail já cadastrado ou falha no banco.")

    return render_template("cadastro.html", erro=None)


# --- ROTA DE LOGIN (AJUSTADA) ---
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email_informado = request.form["email"]
        password_informado = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Consulta buscando o usuário pelo e-mail
        cursor.execute("SELECT * FROM usuario WHERE email = %s", (email_informado,))
        usuario = cursor.fetchone()
        cursor.close()
        conn.close()

        # Se o usuário NÃO foi encontrado
        if not usuario:
            return render_template("login.html", erro="Usuário não encontrado!")

        # Verificação para comparar se as senhas são iguais (usando o hash)
        if check_password_hash(usuario['senha'], password_informado):
            session["user"] = usuario['email']
            return redirect(url_for("listar_filmes"))
        else:
            # Se a senha for diferente
            return render_template("login.html", erro="Senha incorreta!")

    return render_template("login.html", erro=None)


@app.route('/filmes', methods=['GET'])
@login_required
def listar_filmes():
    sql = "SELECT * FROM filmes"
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(sql)
        filmes = cursor.fetchall()
        return render_template("index.html", filmes=filmes)
    except Exception as ex:
        return render_template("erro.html", erro=str(ex))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# Mantive as outras rotas (novo, editar, deletar, logout) iguais para não quebrar seu projeto
@app.route("/novo", methods=["GET", "POST"])
@login_required
def novo_filme():
    sql = "INSERT INTO filmes (titulo, genero, ano, url_capa) VALUES (%s, %s, %s, %s)"
    try:
        if request.method == "POST":
            titulo = request.form["titulo"]
            genero = request.form["genero"]
            ano = request.form["ano"]
            arquivo = request.files.get("imagem")
            if arquivo and allowed_file(arquivo.filename):
                extensao = arquivo.filename.rsplit('.', 1)[1].lower()
                nome_unico = f"{uuid.uuid4().hex}.{extensao}"
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], nome_unico)
                arquivo.save(caminho)
                url_capa = f"uploads/{nome_unico}"
            else:
                return "Arquivo inválido", 400
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, [titulo, genero, ano, url_capa])
            conn.commit()
            conn.close()
            return redirect(url_for("listar_filmes"))
        return render_template("novo_filme.html")
    except Exception as ex:
        return jsonify({"message": "erro ao cadastrar filme"}), 500


@app.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_filme(id):
    try:
        conn = get_connection()
        if request.method == "POST":
            titulo = request.form["titulo"]
            genero = request.form["genero"]
            ano = request.form["ano"]
            arquivo = request.files.get("imagem")
            if arquivo and allowed_file(arquivo.filename):
                extensao = arquivo.filename.rsplit('.', 1)[1].lower()
                nome_unico = f"{uuid.uuid4().hex}.{extensao}"
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], nome_unico)
                arquivo.save(caminho)
                url_capa = f"uploads/{nome_unico}"
            else:
                url_capa = request.form["url_capa"]
            sql_update = "UPDATE filmes SET titulo = %s, genero = %s, ano = %s, url_capa = %s WHERE id = %s"
            cursor = conn.cursor()
            cursor.execute(sql_update, [titulo, genero, ano, url_capa, id])
            conn.commit()
            conn.close()
            return redirect(url_for("listar_filmes"))
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM filmes WHERE id = %s", [id])
        filme = cursor.fetchone()
        conn.close()
        return render_template("editar_filme.html", filme=filme)
    except Exception as ex:
        return jsonify({"message": "erro ao editar"}), 500


@app.route("/deletar/<int:id>", methods=["POST"])
@login_required
def deletar_filme(id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM filmes WHERE id = %s", [id])
        conn.commit()
        conn.close()
        return redirect(url_for("listar_filmes"))
    except Exception:
        return jsonify({"message": "erro ao deletar"}), 500


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


if __name__ == '__main__':
    app.run(debug=True)