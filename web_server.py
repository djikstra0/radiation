from flask import Flask, render_template, jsonify
import psycopg2
import psycopg2.extras

app = Flask(__name__)

# Konfiguracija baze
DB_CONFIG = {
    "host": "localhost",
    "database": "postgres",
    "user": "postgres",
    "password": ""
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


@app.route('/')
def index():
    # Vraća glavni HTML fajl
    return render_template('dashboard.html')


@app.route('/api/realtime')
def realtime():
    conn = None
    cur = None

    try:
        conn = get_db_connection()

        # RealDictCursor nam omogućava da podatke
        # dobijemo kao Python dictionary (JSON)
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        # DISTINCT ON osigurava da uzmemo samo najnoviji red za svaki grad.
        query = """
            SELECT DISTINCT ON (LOWER(l.location_name))
                l.location_name AS city,
                r.time AS measurement_time,
                r.radiation_usv AS usv,
                l.latitude,
                l.longitude,
                l.threshold
            FROM locations l
            JOIN radiation_data r
                ON LOWER(l.location_name) = LOWER(r.location)
            ORDER BY LOWER(l.location_name), r.time DESC;
        """

        cur.execute(query)
        data = cur.fetchall()

        return jsonify(data)

    except Exception as e:
        print(f"Greska pri povlacenju podataka: {e}")
        return jsonify({"error": str(e)}), 500

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()


if __name__ == '__main__':
    # Server radi na http://localhost:5000
    app.run(debug=True, port=5000)
