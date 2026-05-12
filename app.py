from flask import Flask, render_template, request, redirect, Response, session
import psycopg2
import os
import json
from decimal import Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import io

app = Flask(__name__)
app.secret_key = 'gestion_loyers_secret_2026'

USERS = {
    'Kazroua': generate_password_hash('cedric'),
    'Madame Assemian': generate_password_hash('niman')
}

def format_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%d/%m/%y')
    except:
        return value

@app.template_filter('formatdate')
def formatdate(value):
    return format_date(value)

def get_db():
    url = os.environ.get('DATABASE_URL', '')
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    conn = psycopg2.connect(url, sslmode='require')
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS loyers (
        id SERIAL PRIMARY KEY,
        bien TEXT NOT NULL,
        locataire TEXT NOT NULL,
        montant REAL NOT NULL,
        date TEXT NOT NULL,
        statut TEXT NOT NULL,
        commentaire TEXT
    )''')
    conn.commit()
    conn.close()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['GET', 'POST'])
def login():
    erreur = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS and check_password_hash(USERS[username], password):
            session['user'] = username
            return redirect('/')
        else:
            erreur = "Nom d'utilisateur ou mot de passe incorrect"
    return render_template('login.html', erreur=erreur)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

@app.route('/')
@login_required
def index():
    mois = request.args.get('mois', '')
    conn = get_db()
    c = conn.cursor()
    if mois:
        c.execute("SELECT * FROM loyers WHERE date LIKE %s ORDER BY date DESC", (f'{mois}%',))
    else:
        c.execute('SELECT * FROM loyers ORDER BY date DESC')
    loyers = c.fetchall()
    total = sum(l[3] for l in loyers if l[5] == 'Payé')
    if mois:
        c.execute('''SELECT bien, locataire, SUM(montant), COUNT(*), MAX(commentaire)
                     FROM loyers
                     WHERE statut IN (%s, %s)
                     AND date LIKE %s
                     GROUP BY bien, locataire''', ('Impayé', 'En retard', f'{mois}%'))
    else:
        c.execute('''SELECT bien, locataire, SUM(montant), COUNT(*), MAX(commentaire)
                     FROM loyers
                     WHERE statut IN (%s, %s)
                     GROUP BY bien, locataire''', ('Impayé', 'En retard'))
    arrieres = c.fetchall()
    conn.close()
    return render_template('index.html', loyers=loyers,
                           arrieres=arrieres, mois=mois, total=total,
                           user=session['user'])

@app.route('/ajouter', methods=['POST'])
@login_required
def ajouter():
    bien = request.form['bien']
    locataire = request.form['locataire']
    montant = request.form['montant']
    date = request.form['date']
    statut = request.form['statut']
    commentaire = request.form.get('commentaire', '')
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO loyers (bien, locataire, montant, date, statut, commentaire) VALUES (%s, %s, %s, %s, %s, %s)',
              (bien, locataire, montant, date, statut, commentaire))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/modifier/<int:id>')
@login_required
def modifier(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM loyers WHERE id = %s', (id,))
    loyer = c.fetchone()
    conn.close()
    return render_template('modifier.html', loyer=loyer)

@app.route('/modifier/<int:id>', methods=['POST'])
@login_required
def modifier_post(id):
    bien = request.form['bien']
    locataire = request.form['locataire']
    montant = request.form['montant']
    date = request.form['date']
    statut = request.form['statut']
    commentaire = request.form.get('commentaire', '')
    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE loyers SET bien=%s, locataire=%s, montant=%s, date=%s, statut=%s, commentaire=%s
                 WHERE id=%s''', (bien, locataire, montant, date, statut, commentaire, id))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/supprimer/<int:id>')
@login_required
def supprimer(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM loyers WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT CAST(date AS TEXT), CAST(montant AS FLOAT), CAST(statut AS TEXT) FROM loyers")
    rows = c.fetchall()
    conn.close()

    donnees = [{'mois': r[0][:7], 'montant': r[1], 'statut': r[2]} for r in rows]
    donnees_json = json.dumps(donnees)

    total_encaisse = sum(r[1] for r in rows if r[2] == 'Payé')
    total_impayes = sum(r[1] for r in rows if r[2] != 'Payé')
    total = total_encaisse + total_impayes
    taux = round((total_encaisse / total * 100) if total > 0 else 0)

    return render_template('dashboard.html',
                           donnees_json=donnees_json,
                           total_encaisse=total_encaisse,
                           total_impayes=total_impayes,
                           taux=taux,
                           user=session['user'])

@app.route('/recu/<int:id>')
@login_required
def generer_recu(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM loyers WHERE id = %s', (id,))
    loyer = c.fetchone()
    conn.close()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    elements = []
    logo_path = os.path.join('static', 'logo.png')
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=150, height=75)
        elements.append(logo)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("REÇU DE PAIEMENT", styles['Title']))
    elements.append(Spacer(1, 5))
    elements.append(Paragraph(f"N° Reçu : LBR-{id:04d}", styles['Normal']))
    elements.append(Paragraph(f"Date d'émission : {datetime.now().strftime('%d/%m/%Y')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a3c6e')))
    elements.append(Spacer(1, 15))
    data = [
        ['Bien', loyer[1]],
        ['Locataire', loyer[2]],
        ['Montant payé', f"{loyer[3]:,.0f} FCFA"],
        ['Date de paiement', format_date(loyer[4])],
        ['Statut', loyer[5]],
    ]
    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#1a3c6e')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.whitesmoke, colors.white]),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 30))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    elements.append(Spacer(1, 20))
    sig_data = [['Signature du gestionnaire', "Cachet de l'entreprise"]]
    sig_table = Table(sig_data, colWidths=[230, 230])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 10))
    sig_path = os.path.join('static', 'signature.png')
    if os.path.exists(sig_path):
        sig_img = RLImage(sig_path, width=120, height=60)
        cachet_data = [[sig_img, 'Emplacement\ndu cachet']]
    else:
        cachet_data = [['', 'Emplacement\ndu cachet']]
    content_table = Table(cachet_data, colWidths=[230, 230])
    content_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (1, 0), (1, 0), colors.grey),
        ('BOX', (1, 0), (1, 0), 1, colors.grey),
        ('PADDING', (0, 0), (-1, -1), 15),
    ]))
    elements.append(content_table)
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#1a3c6e')))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        "Le Labelle Résidence — Votre confort, notre engagement",
        styles['Normal']
    ))
    doc.build(elements)
    buffer.seek(0)
    filename = f"recu_LBR{id:04d}_{loyer[2].replace(' ', '_')}.pdf"
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment;filename={filename}'})

@app.route('/export-pdf')
@login_required
def export_pdf():
    mois = request.args.get('mois', '')
    conn = get_db()
    c = conn.cursor()
    if mois:
        c.execute("SELECT * FROM loyers WHERE date LIKE %s ORDER BY date DESC", (f'{mois}%',))
    else:
        c.execute('SELECT * FROM loyers ORDER BY date DESC')
    loyers = c.fetchall()
    total = sum(l[3] for l in loyers if l[5] == 'Payé')
    if mois:
        c.execute('''SELECT bien, locataire, SUM(montant), COUNT(*), MAX(commentaire)
                     FROM loyers WHERE statut IN (%s, %s)
                     AND date LIKE %s
                     GROUP BY bien, locataire''', ('Impayé', 'En retard', f'{mois}%'))
    else:
        c.execute('''SELECT bien, locataire, SUM(montant), COUNT(*), MAX(commentaire)
                     FROM loyers WHERE statut IN (%s, %s)
                     GROUP BY bien, locataire''', ('Impayé', 'En retard'))
    arrieres = c.fetchall()
    conn.close()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=30, leftMargin=30,
                            topMargin=40, bottomMargin=30)
    styles = getSampleStyleSheet()
    elements = []
    logo_path = os.path.join('static', 'logo.png')
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=120, height=60)
        elements.append(logo)
    titre = "Rapport de Gestion des Loyers"
    if mois:
        titre += f" — {mois}"
    elements.append(Paragraph(titre, styles['Title']))
    elements.append(Paragraph(f"Généré par : {session['user']}", styles['Normal']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Total encaissé : {total} FCFA", styles['Heading2']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Détail des loyers", styles['Heading2']))
    data = [['Bien', 'Locataire', 'Montant (FCFA)', 'Date', 'Statut', 'Commentaire']]
    for l in loyers:
        commentaire = l[6] if len(l) > 6 and l[6] else '-'
        date_formatee = format_date(l[4])
        data.append([l[1], l[2], f"{l[3]}", date_formatee, l[5], commentaire])
    table = Table(data, colWidths=[90, 100, 85, 70, 65, 90])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a3c6e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))
    if arrieres:
        elements.append(Paragraph("Arriérés de paiement", styles['Heading2']))
        data2 = [['Bien', 'Locataire', 'Total dû (FCFA)', 'Nb mois', 'Commentaire']]
        for a in arrieres:
            commentaire = a[4] if a[4] else '-'
            data2.append([a[0], a[1], f"{a[2]}", f"{a[3]}", commentaire])
        table2 = Table(data2, colWidths=[100, 120, 100, 70, 110])
        table2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c0392b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.mistyrose, colors.white]),
        ]))
        elements.append(table2)
    doc.build(elements)
    buffer.seek(0)
    filename = f"loyers_{mois if mois else 'complet'}.pdf"
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment;filename={filename}'})

@app.route('/manifest.json')
def manifest():
    from flask import send_from_directory
    return send_from_directory('static', 'manifest.json')

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)