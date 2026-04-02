import sqlite3
import io
import os
from datetime import datetime, date
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, send_file, g)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

app = Flask(__name__)
# Clé secrète : variable d'environnement en prod, valeur par défaut en local
app.secret_key = os.environ.get('SECRET_KEY', 'achatpro_secret_local_2024')
# Base de données : dossier /tmp sur Render (persistant dans le disque), local sinon
DATABASE = os.environ.get('DATABASE_PATH',
           os.path.join(os.path.dirname(__file__), 'commandes.db'))

# ── BASE DE DONNÉES ────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with sqlite3.connect(DATABASE) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS fournisseur (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nom       TEXT NOT NULL,
            contact   TEXT,
            email     TEXT,
            telephone TEXT,
            adresse   TEXT,
            siret     TEXT
        );
        CREATE TABLE IF NOT EXISTS commande (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            numero         TEXT UNIQUE NOT NULL,
            date_creation  TEXT NOT NULL,
            statut         TEXT DEFAULT 'Brouillon',
            fournisseur_id INTEGER NOT NULL REFERENCES fournisseur(id),
            notes          TEXT
        );
        CREATE TABLE IF NOT EXISTS ligne_commande (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            commande_id    INTEGER NOT NULL REFERENCES commande(id) ON DELETE CASCADE,
            designation    TEXT NOT NULL,
            reference      TEXT,
            quantite       REAL DEFAULT 1,
            unite          TEXT DEFAULT 'unite',
            prix_unitaire  REAL DEFAULT 0,
            tva            REAL DEFAULT 20
        );
        """)

# ── HELPERS ────────────────────────────────────────────────────────────────────

def generer_numero():
    db = get_db()
    mois = date.today().strftime('%Y%m')
    prefix = f'BC-{mois}-'
    row = db.execute(
        "SELECT COUNT(*) as n FROM commande WHERE numero LIKE ?", (prefix + '%',)
    ).fetchone()
    return f"{prefix}{row['n']+1:04d}"

def get_fournisseur(fid):
    return get_db().execute("SELECT * FROM fournisseur WHERE id=?", (fid,)).fetchone()

def get_commande(cid):
    return get_db().execute(
        "SELECT c.*, f.nom as fourn_nom, f.contact, f.email, f.telephone, "
        "f.adresse, f.siret as fourn_siret "
        "FROM commande c JOIN fournisseur f ON f.id=c.fournisseur_id WHERE c.id=?", (cid,)
    ).fetchone()

def get_lignes(cid):
    return get_db().execute(
        "SELECT * FROM ligne_commande WHERE commande_id=? ORDER BY id", (cid,)
    ).fetchall()

def calc_totaux(lignes):
    ht  = sum(l['quantite'] * l['prix_unitaire'] for l in lignes)
    ttc = sum(l['quantite'] * l['prix_unitaire'] * (1 + l['tva']/100) for l in lignes)
    return ht, ttc

def _save_lignes(db, cid):
    designations   = request.form.getlist('designation')
    references     = request.form.getlist('reference')
    quantites      = request.form.getlist('quantite')
    unites         = request.form.getlist('unite')
    prix_unitaires = request.form.getlist('prix_unitaire')
    tvas           = request.form.getlist('tva')
    for i, desig in enumerate(designations):
        if desig.strip():
            db.execute(
                "INSERT INTO ligne_commande "
                "(commande_id,designation,reference,quantite,unite,prix_unitaire,tva) "
                "VALUES (?,?,?,?,?,?,?)",
                (cid, desig,
                 references[i] if i < len(references) else '',
                 float(quantites[i]) if i < len(quantites) and quantites[i] else 1,
                 unites[i] if i < len(unites) and unites[i] else 'unite',
                 float(prix_unitaires[i]) if i < len(prix_unitaires) and prix_unitaires[i] else 0,
                 float(tvas[i]) if i < len(tvas) and tvas[i] else 20)
            )

# ── ROUTES FOURNISSEURS ────────────────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    nb_f  = db.execute("SELECT COUNT(*) as n FROM fournisseur").fetchone()['n']
    nb_b  = db.execute("SELECT COUNT(*) as n FROM commande WHERE statut='Brouillon'").fetchone()['n']
    nb_e  = db.execute("SELECT COUNT(*) as n FROM commande WHERE statut='Envoyee'").fetchone()['n']
    nb_cl = db.execute("SELECT COUNT(*) as n FROM commande WHERE statut='Cloturee'").fetchone()['n']
    rows  = db.execute(
        "SELECT c.*, f.nom as fourn_nom FROM commande c "
        "JOIN fournisseur f ON f.id=c.fournisseur_id "
        "ORDER BY c.date_creation DESC LIMIT 5"
    ).fetchall()
    dernieres = []
    for c in rows:
        lignes = get_lignes(c['id'])
        ht, ttc = calc_totaux(lignes)
        dernieres.append({**dict(c), 'total_ht': ht, 'total_ttc': ttc})
    return render_template('index.html',
        nb_fournisseurs=nb_f,
        nb_brouillons=nb_b, nb_envoyees=nb_e, nb_cloturees=nb_cl,
        dernieres=dernieres)

@app.route('/fournisseurs')
def fournisseurs():
    liste = get_db().execute("SELECT * FROM fournisseur ORDER BY nom").fetchall()
    return render_template('fournisseurs.html', fournisseurs=liste)

@app.route('/fournisseurs/nouveau', methods=['GET','POST'])
def nouveau_fournisseur():
    if request.method == 'POST':
        db = get_db()
        db.execute(
            "INSERT INTO fournisseur (nom,contact,email,telephone,adresse,siret) VALUES (?,?,?,?,?,?)",
            (request.form['nom'], request.form.get('contact'), request.form.get('email'),
             request.form.get('telephone'), request.form.get('adresse'), request.form.get('siret'))
        )
        db.commit()
        flash('Fournisseur cree avec succes.', 'success')
        return redirect(url_for('fournisseurs'))
    return render_template('fournisseur_form.html', fournisseur=None)

@app.route('/fournisseurs/<int:fid>/modifier', methods=['GET','POST'])
def modifier_fournisseur(fid):
    f = get_fournisseur(fid)
    if f is None:
        flash('Fournisseur introuvable.', 'danger')
        return redirect(url_for('fournisseurs'))
    if request.method == 'POST':
        db = get_db()
        db.execute(
            "UPDATE fournisseur SET nom=?,contact=?,email=?,telephone=?,adresse=?,siret=? WHERE id=?",
            (request.form['nom'], request.form.get('contact'), request.form.get('email'),
             request.form.get('telephone'), request.form.get('adresse'), request.form.get('siret'), fid)
        )
        db.commit()
        flash('Fournisseur mis a jour.', 'success')
        return redirect(url_for('fournisseurs'))
    return render_template('fournisseur_form.html', fournisseur=f)

@app.route('/fournisseurs/<int:fid>/supprimer', methods=['POST'])
def supprimer_fournisseur(fid):
    db = get_db()
    db.execute("DELETE FROM fournisseur WHERE id=?", (fid,))
    db.commit()
    flash('Fournisseur supprime.', 'warning')
    return redirect(url_for('fournisseurs'))

# ── ROUTES COMMANDES ───────────────────────────────────────────────────────────

@app.route('/commandes')
def commandes():
    db = get_db()

    # Parametres de filtre
    statut         = request.args.get('statut', '').strip()
    q              = request.args.get('q', '').strip()
    fournisseur_id = request.args.get('fournisseur_id', '').strip()
    date_debut     = request.args.get('date_debut', '').strip()
    date_fin       = request.args.get('date_fin', '').strip()
    tri            = request.args.get('tri', 'date_desc')

    # Requete dynamique
    sql    = ("SELECT c.*, f.nom as fourn_nom FROM commande c "
              "JOIN fournisseur f ON f.id=c.fournisseur_id WHERE 1=1")
    params = []

    if statut:
        sql += " AND c.statut=?"; params.append(statut)
    if fournisseur_id:
        sql += " AND c.fournisseur_id=?"; params.append(int(fournisseur_id))
    if q:
        like = f'%{q}%'
        sql += " AND (c.numero LIKE ? OR f.nom LIKE ? OR c.notes LIKE ?)"
        params += [like, like, like]
    if date_debut:
        sql += " AND c.date_creation >= ?"; params.append(date_debut + ' 00:00:00')
    if date_fin:
        sql += " AND c.date_creation <= ?"; params.append(date_fin + ' 23:59:59')

    ordre = {
        'date_desc': 'c.date_creation DESC',
        'date_asc':  'c.date_creation ASC',
        'num_desc':  'c.numero DESC',
        'num_asc':   'c.numero ASC',
        'fourn_asc': 'f.nom ASC',
    }.get(tri, 'c.date_creation DESC')
    sql += f" ORDER BY {ordre}"

    rows = db.execute(sql, params).fetchall()
    fournisseurs_list = db.execute("SELECT id, nom FROM fournisseur ORDER BY nom").fetchall()

    liste = []
    for c in rows:
        lignes = get_lignes(c['id'])
        ht, ttc = calc_totaux(lignes)
        liste.append({**dict(c), 'total_ht': ht, 'total_ttc': ttc, 'nb_lignes': len(lignes)})

    filtres_actifs = bool(statut or q or fournisseur_id or date_debut or date_fin)

    return render_template('commandes.html',
        commandes=liste,
        statut_filtre=statut,
        q=q,
        fournisseur_id=fournisseur_id,
        date_debut=date_debut,
        date_fin=date_fin,
        tri=tri,
        fournisseurs_list=fournisseurs_list,
        filtres_actifs=filtres_actifs,
    )

@app.route('/commandes/nouvelle', methods=['GET','POST'])
def nouvelle_commande():
    db = get_db()
    fournisseurs_list = db.execute("SELECT * FROM fournisseur ORDER BY nom").fetchall()
    if not fournisseurs_list:
        flash("Veuillez d'abord creer un fournisseur.", 'warning')
        return redirect(url_for('nouveau_fournisseur'))
    if request.method == 'POST':
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        cur = db.execute(
            "INSERT INTO commande (numero,date_creation,statut,fournisseur_id,notes) VALUES (?,?,?,?,?)",
            (generer_numero(), now, 'Brouillon',
             int(request.form['fournisseur_id']), request.form.get('notes'))
        )
        cid = cur.lastrowid
        _save_lignes(db, cid)
        db.commit()
        flash('Commande creee.', 'success')
        return redirect(url_for('detail_commande', cid=cid))
    return render_template('commande_form.html', commande=None,
                           fournisseurs=fournisseurs_list, lignes=[])

@app.route('/commandes/<int:cid>')
def detail_commande(cid):
    c = get_commande(cid)
    if c is None:
        flash('Commande introuvable.', 'danger')
        return redirect(url_for('commandes'))
    lignes = get_lignes(cid)
    ht, ttc = calc_totaux(lignes)
    return render_template('commande_detail.html', commande=c, lignes=lignes,
                           total_ht=ht, total_ttc=ttc, total_tva=ttc-ht)

@app.route('/commandes/<int:cid>/modifier', methods=['GET','POST'])
def modifier_commande(cid):
    db = get_db()
    c = get_commande(cid)
    if c is None:
        flash('Commande introuvable.', 'danger')
        return redirect(url_for('commandes'))
    fournisseurs_list = db.execute("SELECT * FROM fournisseur ORDER BY nom").fetchall()
    if request.method == 'POST':
        db.execute("UPDATE commande SET fournisseur_id=?,notes=? WHERE id=?",
            (int(request.form['fournisseur_id']), request.form.get('notes'), cid))
        db.execute("DELETE FROM ligne_commande WHERE commande_id=?", (cid,))
        _save_lignes(db, cid)
        db.commit()
        flash('Commande mise a jour.', 'success')
        return redirect(url_for('detail_commande', cid=cid))
    lignes = get_lignes(cid)
    return render_template('commande_form.html', commande=c,
                           fournisseurs=fournisseurs_list, lignes=lignes)

@app.route('/commandes/<int:cid>/statut/<statut>', methods=['POST'])
def changer_statut(cid, statut):
    if statut in ('Brouillon', 'Envoyee', 'Cloturee'):
        db = get_db()
        db.execute("UPDATE commande SET statut=? WHERE id=?", (statut, cid))
        db.commit()
        flash(f'Statut mis a jour : {statut}.', 'success')
    return redirect(url_for('detail_commande', cid=cid))

@app.route('/commandes/<int:cid>/supprimer', methods=['POST'])
def supprimer_commande(cid):
    db = get_db()
    db.execute("DELETE FROM commande WHERE id=?", (cid,))
    db.commit()
    flash('Commande supprimee.', 'warning')
    return redirect(url_for('commandes'))

# ── GÉNÉRATION PDF ─────────────────────────────────────────────────────────────

SOCIETE = {
    'nom':     'Ma Societe SAS',
    'adresse': '12 rue de la Paix\n75001 Paris',
    'siret':   '123 456 789 00012',
    'tel':     '01 23 45 67 89',
    'email':   'contact@masociete.fr',
}

def build_pdf(commande, lignes, total_ht, total_ttc):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=20*mm)
    story = []

    def mk(name, **kw): return ParagraphStyle(name, **kw)
    s_soc   = mk('soc', fontSize=16, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a2e'))
    s_sub   = mk('sub', fontSize=8,  fontName='Helvetica',      textColor=colors.HexColor('#555555'), leading=12)
    s_titre = mk('tit', fontSize=22, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a2e'), alignment=TA_RIGHT)
    s_num   = mk('num', fontSize=10, fontName='Helvetica',      textColor=colors.HexColor('#444444'), alignment=TA_RIGHT)
    s_lbl   = mk('lbl', fontSize=8,  fontName='Helvetica-Bold', textColor=colors.HexColor('#888888'))
    s_fourn = mk('fou', fontSize=10, fontName='Helvetica',      textColor=colors.HexColor('#1a1a2e'), leading=14)
    s_th    = mk('th',  fontSize=9,  fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER)
    s_td    = mk('td',  fontSize=9,  fontName='Helvetica',      leading=12)
    s_tdr   = mk('tdr', fontSize=9,  fontName='Helvetica',      alignment=TA_RIGHT, leading=12)
    s_totr  = mk('tor', fontSize=10, fontName='Helvetica',      alignment=TA_RIGHT)
    s_totv  = mk('tov', fontSize=10, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    s_ttcl  = mk('ttc', fontSize=12, fontName='Helvetica-Bold', alignment=TA_RIGHT, textColor=colors.white)
    s_notl  = mk('notl',fontSize=8,  fontName='Helvetica-Bold', textColor=colors.HexColor('#888888'))
    s_not   = mk('not', fontSize=9,  fontName='Helvetica',      textColor=colors.HexColor('#333333'), leading=14)
    s_foot  = mk('ft',  fontSize=7,  fontName='Helvetica',      textColor=colors.HexColor('#999999'), alignment=TA_CENTER)

    try:
        date_str = datetime.strptime(commande['date_creation'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
    except Exception:
        date_str = str(commande['date_creation'])[:10]

    # En-tête société / titre BC
    soc_info = (f"{SOCIETE['adresse'].replace(chr(10),'<br/>')}<br/>"
                f"SIRET : {SOCIETE['siret']}<br/>"
                f"Tel : {SOCIETE['tel']}<br/>"
                f"Email : {SOCIETE['email']}")
    bc_num = (f"N <b>{commande['numero']}</b><br/>"
              f"Date : {date_str}<br/>"
              f"Statut : <b>{commande['statut']}</b>")
    hdr = Table([
        [Paragraph(SOCIETE['nom'], s_soc),  Paragraph("BON DE COMMANDE", s_titre)],
        [Paragraph(soc_info, s_sub),        Paragraph(bc_num, s_num)],
    ], colWidths=[90*mm, 80*mm])
    hdr.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(1,0),(1,-1),'RIGHT'),
        ('BOTTOMPADDING',(0,0),(-1,-1),3),
    ]))
    story += [hdr, HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a1a2e'), spaceAfter=8)]

    # Bloc fournisseur
    fl = f"<b>{commande['fourn_nom']}</b>"
    if commande['adresse']:  fl += f"<br/>{commande['adresse'].replace(chr(10),'<br/>')}"
    if commande['fourn_siret']: fl += f"<br/>SIRET : {commande['fourn_siret']}"
    if commande['email']:    fl += f"<br/>{commande['email']}"
    if commande['telephone']:fl += f"<br/>{commande['telephone']}"
    fb = Table([[Paragraph("FOURNISSEUR",s_lbl)],[Paragraph(fl,s_fourn)]], colWidths=[170*mm])
    fb.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),.5,colors.HexColor('#cccccc')),
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f8f9fa')),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    story += [fb, Spacer(1, 8*mm)]

    # Tableau des lignes
    data = [[Paragraph(t, s_th) for t in ['Designation','Ref.','Qte','Unite','P.U. HT','TVA','Total HT']]]
    for l in lignes:
        hl = l['quantite'] * l['prix_unitaire']
        data.append([
            Paragraph(l['designation'], s_td),
            Paragraph(l['reference'] or '', s_td),
            Paragraph(f"{l['quantite']:g}", s_tdr),
            Paragraph(l['unite'], s_td),
            Paragraph(f"{l['prix_unitaire']:,.2f} EUR", s_tdr),
            Paragraph(f"{l['tva']:g}%", s_tdr),
            Paragraph(f"{hl:,.2f} EUR", s_tdr),
        ])
    lt = Table(data, colWidths=[65*mm,22*mm,14*mm,16*mm,20*mm,13*mm,20*mm], repeatRows=1)
    lt.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1a1a2e')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, colors.HexColor('#f4f6fb')]),
        ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#dddddd')),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
    ]))
    story += [lt, Spacer(1, 6*mm)]

    # Totaux
    tva_t = total_ttc - total_ht
    td = [
        [Paragraph("Total HT", s_totr),  Paragraph(f"{total_ht:,.2f} EUR", s_totv)],
        [Paragraph("Total TVA", s_totr), Paragraph(f"{tva_t:,.2f} EUR", s_totv)],
        [Paragraph("TOTAL TTC", s_ttcl), Paragraph(f"{total_ttc:,.2f} EUR", s_ttcl)],
    ]
    tt = Table(td, colWidths=[40*mm,35*mm], hAlign='RIGHT')
    tt.setStyle(TableStyle([
        ('ALIGN',(0,0),(-1,-1),'RIGHT'),
        ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('LINEABOVE',(0,2),(-1,2),.5,colors.HexColor('#cccccc')),
        ('BACKGROUND',(0,2),(-1,2),colors.HexColor('#1a1a2e')),
    ]))
    story.append(tt)

    # Notes
    if commande['notes']:
        story.append(Spacer(1,8*mm))
        nb = Table([[Paragraph("NOTES / CONDITIONS",s_notl)],[Paragraph(commande['notes'],s_not)]],
                   colWidths=[170*mm])
        nb.setStyle(TableStyle([
            ('BOX',(0,0),(-1,-1),.5,colors.HexColor('#cccccc')),
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f8f9fa')),
            ('LEFTPADDING',(0,0),(-1,-1),8),
            ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ]))
        story.append(nb)

    # Pied
    story += [
        Spacer(1,10*mm),
        HRFlowable(width="100%", thickness=.5, color=colors.HexColor('#cccccc')),
        Spacer(1,3*mm),
        Paragraph(f"{SOCIETE['nom']} - SIRET {SOCIETE['siret']} - "
                  f"{SOCIETE['adresse'].replace(chr(10),', ')}", s_foot),
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer

@app.route('/commandes/<int:cid>/pdf')
def telecharger_pdf(cid):
    c = get_commande(cid)
    if c is None:
        flash('Commande introuvable.', 'danger')
        return redirect(url_for('commandes'))
    lignes = get_lignes(cid)
    ht, ttc = calc_totaux(lignes)
    buf = build_pdf(c, lignes, ht, ttc)
    return send_file(buf, as_attachment=True,
                     download_name=f"{c['numero']}.pdf",
                     mimetype='application/pdf')

# ── DÉMARRAGE ──────────────────────────────────────────────────────────────────
# init_db() est appelé au chargement du module (fonctionne avec gunicorn ET python app.py)
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
