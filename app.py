from flask import Flask, render_template, request, redirect, Response, session
import sqlite3
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import io
import os

app = Flask(__name__)
app.secret_key = 'gestion_loyers_secret_2026'

USERS = {
    'Kazroua': generate_password_hash('immo2026'),
    'Mme Anita Corine epse Assemian': generate_password_hash('immo2026')
}

def format_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%d/%m/%y')
    except:
        return value

@app.template_filter('formatdate')
def formatdate(value):
    return format_date(value)

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS loyers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bien TEXT NOT NULL,
        locataire TEXT NOT NULL,
        montant REAL NOT NULL,
        date TEXT NOT NULL,
        statut TEXT NOT NULL,
        commentaire TEXT
    )''')
    try:
        c.execute('ALTER TABLE loyers ADD COLUMN commentaire TEXT')
    except:
        pass
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
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if mois:
        c.execute('SELECT * FROM loyers WHERE date LIKE ? ORDER BY date DESC', (f'{mois}%',))
    else:
        c.execute('SELECT * FROM loyers ORDER BY date DESC')
    loyers = c.fetchall()
    total = sum(l[3] for l in loyers if l[5] == 'Payé')
    if mois:
        c.execute('''SELECT bien, locataire, SUM(montant), COUNT(*), MAX(commentaire)
                     FROM loyers
                     WHERE statut IN ("Impayé", "En retard")
                     AND date LIKE ?
                     GROUP BY bien, locataire''', (f'{mois}%',))
    else:
        c.execute('''SELECT bien, locataire, SUM(montant), COUNT(*), MAX(commentaire)
                     FROM loyers
                     WHERE statut IN ("Impayé", "En retard")
                     GROUP BY bien, locataire''')
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
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('INSERT INTO loyers (bien, locataire, montant, date, statut, commentaire) VALUES (?, ?, ?, ?, ?, ?)',
              (bien, locataire, montant, date, statut, commentaire))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/modifier/<int:id>')
@login_required
def modifier(id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT * FROM loyers WHERE id = ?', (id,))
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
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''UPDATE loyers SET bien=?, locataire=?, montant=?, date=?, statut=?, commentaire=?
                 WHERE id=?''', (bien, locataire, montant, date, statut, commentaire, id))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/supprimer/<int:id>')
@login_required
def supprimer(id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('DELETE FROM loyers WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/export-pdf')
@login_required
def export_pdf():
    mois = request.args.get('mois', '')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if mois:
        c.execute('SELECT * FROM loyers WHERE date LIKE ? ORDER BY date DESC', (f'{mois}%',))
    else:
        c.execute('SELECT * FROM loyers ORDER BY date DESC')
    loyers = c.fetchall()
    total = sum(l[3] for l in loyers if l[5] == 'Payé')
    if mois:
        c.execute('''SELECT bien, locataire, SUM(montant), COUNT(*), MAX(commentaire)
                     FROM loyers
                     WHERE statut IN ("Impayé", "En retard")
                     AND date LIKE ?
                     GROUP BY bien, locataire''', (f'{mois}%',))
    else:
        c.execute('''SELECT bien, locataire, SUM(montant), COUNT(*), MAX(commentaire)
                     FROM loyers
                     WHERE statut IN ("Impayé", "En retard")
                     GROUP BY bien, locataire''')
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True)