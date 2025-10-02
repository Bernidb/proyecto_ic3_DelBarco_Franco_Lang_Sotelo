import sqlite3

# Crear conexión a la base de datos
conn = sqlite3.connect("locknet.db")
cursor = conn.cursor()

# Tabla usuarios
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
)
""")

# Tabla cerraduras
cursor.execute("""
CREATE TABLE IF NOT EXISTS cerraduras (
    id_cerradura INTEGER PRIMARY KEY AUTOINCREMENT,
    habitacion TEXT NOT NULL UNIQUE,
    estado_actual TEXT NOT NULL
)
""")

# Tabla tokens
cursor.execute("""
CREATE TABLE IF NOT EXISTS tokens (
    id_token INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER,
    id_cerradura INTEGER,
    token TEXT UNIQUE NOT NULL,
    fecha_inicio TEXT NOT NULL,
    fecha_fin TEXT NOT NULL,
    estado TEXT NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_cerradura) REFERENCES cerraduras(id_cerradura)
)
""")

# Tabla accesos
cursor.execute("""
CREATE TABLE IF NOT EXISTS accesos (
    id_acceso INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cerradura INTEGER,
    id_usuario INTEGER,
    token_usado TEXT NOT NULL,
    fecha_hora TEXT NOT NULL,
    resultado TEXT NOT NULL,
    FOREIGN KEY (id_cerradura) REFERENCES cerraduras(id_cerradura),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
)
""")

conn.commit()
conn.close()

print("Base de datos creada correctamente ✅")
