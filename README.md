# AchatPro — Gestion des commandes fournisseurs

Application web Flask pour gérer vos bons de commande fournisseurs.

## Fonctionnalités

- ✅ Gestion des fournisseurs (CRUD)
- ✅ Création de bons de commande avec lignes dynamiques
- ✅ Calcul automatique HT / TVA / TTC
- ✅ Statuts : Brouillon → Envoyée → Clôturée
- ✅ Génération PDF avec en-tête entreprise
- ✅ Tableau de bord avec indicateurs
- ✅ Base de données SQLite locale

## Installation

```bash
# 1. Créer un environnement virtuel (recommandé)
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Lancer l'application
python app.py
```

## Accès

Ouvrir dans le navigateur : **http://localhost:5000**

## Personnalisation

Pour changer le nom/coordonnées de votre société dans les PDF,
modifiez le dictionnaire `SOCIETE` en haut du fichier `app.py` :

```python
SOCIETE = {
    'nom':     'Ma Société SAS',
    'adresse': '12 rue de la Paix\n75001 Paris',
    'siret':   '123 456 789 00012',
    'tel':     '01 23 45 67 89',
    'email':   'contact@masociete.fr',
}
```

## Structure

```
purchase_app/
├── app.py              # Application principale (routes, modèles, PDF)
├── requirements.txt    # Dépendances Python
├── commandes.db        # Base SQLite (créée automatiquement)
└── templates/
    ├── base.html
    ├── index.html
    ├── fournisseurs.html
    ├── fournisseur_form.html
    ├── commandes.html
    ├── commande_form.html
    └── commande_detail.html
```
