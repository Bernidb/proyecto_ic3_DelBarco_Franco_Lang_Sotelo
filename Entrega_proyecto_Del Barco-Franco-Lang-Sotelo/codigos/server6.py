# server5.py (versión con UI web)
from flask import Flask, request, jsonify, render_template, redirect, url_for
import sqlite3
import uuid
import datetime
import paho.mqtt.client as mqtt
import threading
import time

# ----------------------------
# CONFIGURACIÓN MQTT
# ----------------------------
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "locknet/"

# ----------------------------
# DB PATH
# ----------------------------
DB_PATH = "locknet.db"

# ----------------------------
# VALIDACIÓN DE TOKENS DESDE DB
# ----------------------------
def validar_token_db(token, habitacion):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()

    cursor.execute("""
        SELECT t.id_token, t.estado, t.fecha_inicio, t.fecha_fin, u.id_usuario, c.id_cerradura
        FROM tokens t
        JOIN usuarios u ON t.id_usuario = u.id_usuario
        JOIN cerraduras c ON t.id_cerradura = c.id_cerradura
        WHERE t.token=? AND c.habitacion=?
    """, (token, habitacion))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"resultado": "rechazado", "motivo": "Token no encontrado"}

    id_token, estado, inicio, fin, id_usuario, id_cerradura = row

    if estado != "activo":
        conn.close()
        return {"resultado": "rechazado", "motivo": "Token no activo"}

    if not (inicio <= now <= fin):
        conn.close()
        return {"resultado": "rechazado", "motivo": "Token expirado"}

    # Registrar acceso aprobado
    cursor.execute("""
        INSERT INTO accesos (id_cerradura, id_usuario, token_usado, fecha_hora, resultado)
        VALUES (?, ?, ?, ?, ?)
    """, (id_cerradura, id_usuario, token, now, "aprobado"))
    conn.commit()
    conn.close()

    return {"resultado": "aprobado", "motivo": "Acceso válido"}


def registrar_acceso_fallido(token, habitacion, motivo):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()

    cursor.execute("SELECT id_cerradura FROM cerraduras WHERE habitacion=?", (habitacion,))
    cerradura_row = cursor.fetchone()
    cerradura_id = cerradura_row[0] if cerradura_row else None

    cursor.execute("SELECT id_usuario FROM tokens WHERE token=?", (token,))
    usuario_row = cursor.fetchone()
    usuario_id = usuario_row[0] if usuario_row else None

    cursor.execute("""
        INSERT INTO accesos (id_cerradura, id_usuario, token_usado, fecha_hora, resultado)
        VALUES (?, ?, ?, ?, ?)
    """, (cerradura_id, usuario_id, token, now, f"rechazado ({motivo})"))
    conn.commit()
    conn.close()

# ----------------------------
# MQTT CALLBACKS
# ----------------------------
def on_connect(client, userdata, flags, rc):
    print("[MQTT] Conectado al broker.")
    client.subscribe(f"{MQTT_TOPIC_PREFIX}+/validacion")  # escucha validaciones de todas las cerraduras

def on_message(client, userdata, msg):
    try:
        topic = msg.topic  # ej: locknet/101/validacion
        payload = msg.payload.decode()

        print(f"[MQTT] Mensaje recibido en {topic}: {payload}")

        parts = topic.split("/")
        if len(parts) == 3 and parts[2] == "validacion":
            habitacion = parts[1]
            token = payload.strip()

            result = validar_token_db(token, habitacion)

            if result["resultado"] == "aprobado":
                response = "aprobado"
            else:
                response = "rechazado"
                registrar_acceso_fallido(token, habitacion, result["motivo"])

            response_topic = f"{MQTT_TOPIC_PREFIX}{habitacion}/estado"
            client.publish(response_topic, response)
            print(f"[MQTT] Respuesta enviada a {response_topic}: {response}")

    except Exception as e:
        print(f"[ERROR] en on_message: {e}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
except Exception as e:
    print(f"[WARN] No se pudo conectar al broker MQTT: {e}")

thread_mqtt = threading.Thread(target=client.loop_forever)
thread_mqtt.daemon = True
thread_mqtt.start()

# ----------------------------
# FUNCIONES DB
# ----------------------------
def listar_cerraduras_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id_cerradura, habitacion, estado_actual FROM cerraduras")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "habitacion": r[1], "estado": r[2]} for r in rows]

def revocar_token_db(token):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM tokens WHERE token=?", (token,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Token no encontrado"}
    if row[0] != "activo":
        conn.close()
        return {"error": "El token no está activo"}
    cursor.execute("UPDATE tokens SET estado='revocado' WHERE token=?", (token,))
    conn.commit()
    conn.close()
    return {"status": "ok", "mensaje": "Token revocado correctamente"}

def crear_cerradura_db(habitacion):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id_cerradura FROM cerraduras WHERE habitacion = ?", (habitacion,))
    if cursor.fetchone():
        conn.close()
        return None
    cursor.execute("INSERT INTO cerraduras (habitacion, estado_actual) VALUES (?, ?)", (habitacion, "libre"))
    conn.commit()
    conn.close()
    return habitacion

def expirar_tokens():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.execute("""
        UPDATE tokens
        SET estado='expirado'
        WHERE estado='activo' AND fecha_fin <= ?
    """, (now,))
    conn.commit()
    conn.close()
    print("[DB] Tokens expirados actualizados.")

def crear_reserva_db(usuario, habitacion, dias_validez=3):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id_cerradura FROM cerraduras WHERE habitacion = ?", (habitacion,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return {"error": "Habitación no existe"}
    cerradura_id = result[0]

    cursor.execute("""
        SELECT id_token FROM tokens
        WHERE id_cerradura=? AND estado='activo'
        AND fecha_fin > ?
    """, (cerradura_id, datetime.datetime.now().isoformat()))
    if cursor.fetchone():
        conn.close()
        return {"error": "Ya existe una reserva activa en esta habitación"}

    cursor.execute("SELECT id_usuario FROM usuarios WHERE nombre=?", (usuario,))
    result = cursor.fetchone()
    if result:
        usuario_id = result[0]
    else:
        cursor.execute("INSERT INTO usuarios (nombre, email) VALUES (?,?)", (usuario, f"{usuario}@demo.com"))
        usuario_id = cursor.lastrowid

    token = str(uuid.uuid4())
    fecha_inicio = datetime.datetime.now()
    fecha_fin = fecha_inicio + datetime.timedelta(days=dias_validez)

    cursor.execute("""
        INSERT INTO tokens (id_usuario, id_cerradura, token, fecha_inicio, fecha_fin, estado)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (usuario_id, cerradura_id, token, fecha_inicio.isoformat(), fecha_fin.isoformat(), "activo"))

    conn.commit()
    conn.close()

    topic = f"{MQTT_TOPIC_PREFIX}{habitacion}/token"
    try:
        client.publish(topic, token)
    except Exception as e:
        print(f"[WARN] No se pudo publicar token por MQTT: {e}")

    return {"usuario": usuario, "habitacion": habitacion, "token": token, "inicio": fecha_inicio.isoformat(), "fin": fecha_fin.isoformat()}

def listar_tokens_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.token, u.nombre, c.habitacion, t.fecha_inicio, t.fecha_fin, t.estado
        FROM tokens t
        JOIN usuarios u ON t.id_usuario = u.id_usuario
        JOIN cerraduras c ON t.id_cerradura = c.id_cerradura
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"token": r[0], "usuario": r[1], "habitacion": r[2], "inicio": r[3], "fin": r[4], "estado": r[5]} for r in rows]

def listar_accesos_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id_acceso, c.habitacion, u.nombre, a.token_usado, a.fecha_hora, a.resultado
        FROM accesos a
        LEFT JOIN cerraduras c ON a.id_cerradura = c.id_cerradura
        LEFT JOIN usuarios u ON a.id_usuario = u.id_usuario
        ORDER BY a.fecha_hora DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "habitacion": r[1], "usuario": r[2], "token": r[3], "fecha_hora": r[4], "resultado": r[5]} for r in rows]

# ----------------------------
# FLASK APP
# ----------------------------
app = Flask(__name__)

# ---- API JSON existentes ----
@app.route("/listarcerraduras", methods=["GET"])
def listar_cerraduras():
    return jsonify(listar_cerraduras_db())

@app.route("/tokens/<token>", methods=["DELETE"])
def revocar_token(token):
    result = revocar_token_db(token)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route("/cerraduras", methods=["POST"])
def crear_cerradura():
    data = request.json
    habitacion = data.get("habitacion")
    if not habitacion:
        return jsonify({"error": "habitacion requerida"}), 400
    result = crear_cerradura_db(habitacion)
    if result:
        return jsonify({"status": "ok", "habitacion": habitacion})
    else:
        return jsonify({"error": "Habitación ya existe"}), 400

@app.route("/reservas", methods=["POST"])
def crear_reserva():
    data = request.json
    usuario = data.get("usuario")
    habitacion = data.get("habitacion")
    if not usuario or not habitacion:
        return jsonify({"error": "usuario y habitacion requeridos"}), 400
    result = crear_reserva_db(usuario, habitacion)
    return jsonify(result)

@app.route("/tokens", methods=["GET"])
def listar_tokens():
    return jsonify(listar_tokens_db())

@app.route("/accesos", methods=["GET"])
def listar_accesos():
    return jsonify(listar_accesos_db())

# ---- RUTAS WEB (UI) ----
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/cerraduras_web")
def cerraduras_web():
    data = listar_cerraduras_db()
    return render_template("cerraduras.html", cerraduras=data)

@app.route("/crear_cerradura_form", methods=["POST"])
def crear_cerradura_form():
    habitacion = request.form.get("habitacion")
    if habitacion:
        crear_cerradura_db(habitacion)
    return redirect(url_for('cerraduras_web'))

@app.route("/tokens_web")
def tokens_web():
    data = listar_tokens_db()
    return render_template("tokens.html", tokens=data)

@app.route("/crear_reserva_form", methods=["POST"])
def crear_reserva_form():
    usuario = request.form.get("usuario")
    habitacion = request.form.get("habitacion")
    if usuario and habitacion:
        crear_reserva_db(usuario, habitacion)
    return redirect(url_for('tokens_web'))

@app.route("/accesos_web")
def accesos_web():
    data = listar_accesos_db()
    return render_template("accesos.html", accesos=data)

@app.route("/revocar/<token>")
def revocar_web(token):
    revocar_token_db(token)
    return redirect(url_for("tokens_web"))

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    def hilo_expiracion():
        while True:
            expirar_tokens()
            time.sleep(300)  # cada 5 minutos
    threading.Thread(target=hilo_expiracion, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
