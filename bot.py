from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import psycopg2


TOKEN = ""

DB_CONFIG = {
    "host": "localhost",
    "database": "postgres",
    "user": "postgres",
    "password": ""
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


#########################################################
# /start
#########################################################

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO users (chat_id)
        VALUES (%s)
        ON CONFLICT (chat_id) DO NOTHING
    """, (chat_id,))

    conn.commit()

    cur.close()
    conn.close()

    await update.message.reply_text(
        "Registrovan si!\n"
        "Komande:\n"
        "/subscribe <grad>\n"
        "/unsubscribe <grad>\n"
        "/list"
    )


#########################################################
# /subscribe
#########################################################

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Koristi: /subscribe <grad>"
        )
        return

    chat_id = update.effective_chat.id

    # Tehnicki naziv lokacije
    location_code = context.args[0].lower()

    conn = get_conn()
    cur = conn.cursor()

    # Pronadji korisnika
    cur.execute(
        "SELECT id FROM users WHERE chat_id=%s",
        (chat_id,)
    )

    result = cur.fetchone()

    if not result:
        await update.message.reply_text(
            "Nisi registrovan. Prvo ukucaj /start"
        )

        cur.close()
        conn.close()
        return

    user_id = result[0]

    # Proveri da li lokacija postoji
    cur.execute("""
        SELECT location_name
        FROM locations
        WHERE location_code = %s
    """, (location_code,))

    location = cur.fetchone()

    if not location:
        await update.message.reply_text(
            f"Lokacija '{location_code}' ne postoji."
        )

        cur.close()
        conn.close()
        return

    location_name = location[0]

    # Dodaj pretplatu
    cur.execute("""
        INSERT INTO subscriptions (user_id, city)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (user_id, location_code))

    conn.commit()

    cur.close()
    conn.close()

    await update.message.reply_text(
        f"Pretplacen si na {location_name}."
    )


#########################################################
# /unsubscribe
#########################################################

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Koristi: /unsubscribe <grad>"
        )
        return

    chat_id = update.effective_chat.id
    location_code = context.args[0].lower()

    conn = get_conn()
    cur = conn.cursor()

    # Pronadji korisnika
    cur.execute(
        "SELECT id FROM users WHERE chat_id=%s",
        (chat_id,)
    )

    result = cur.fetchone()

    if not result:
        await update.message.reply_text(
            "Nisi registrovan. Koristi /start"
        )

        cur.close()
        conn.close()
        return

    user_id = result[0]

    # Obrisi pretplatu
    cur.execute("""
        DELETE FROM subscriptions
        WHERE user_id = %s
          AND city = %s
    """, (user_id, location_code))

    deleted = cur.rowcount

    conn.commit()

    cur.close()
    conn.close()

    if deleted:
        await update.message.reply_text(
            f"Izbrisana pretplata sa {location_code}."
        )
    else:
        await update.message.reply_text(
            f"Nisi pretplacen na {location_code}."
        )


#########################################################
# /list
#########################################################

async def list_subscriptions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    chat_id = update.effective_chat.id

    conn = get_conn()
    cur = conn.cursor()

    # Pronadji korisnika
    cur.execute(
        "SELECT id FROM users WHERE chat_id=%s",
        (chat_id,)
    )

    result = cur.fetchone()

    if not result:
        await update.message.reply_text(
            "Nisi registrovan. Koristi /start"
        )

        cur.close()
        conn.close()
        return

    user_id = result[0]

    # Uzmi lepo ime lokacije
    cur.execute("""
        SELECT l.location_name
        FROM subscriptions s
        JOIN locations l
            ON s.city = l.location_code
        WHERE s.user_id = %s
        ORDER BY l.location_name
    """, (user_id,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "Nemas nijednu pretplatu."
        )
        return

    locations = [
        row[0]
        for row in rows
    ]

    message = (
        "Pretplacen si na:\n"
        + "\n".join(
            f"- {location}"
            for location in locations
        )
    )

    await update.message.reply_text(message)


#########################################################
# APPLICATION
#########################################################

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(
    CommandHandler("start", start)
)

app.add_handler(
    CommandHandler("subscribe", subscribe)
)

app.add_handler(
    CommandHandler("unsubscribe", unsubscribe)
)

app.add_handler(
    CommandHandler("list", list_subscriptions)
)

app.run_polling()