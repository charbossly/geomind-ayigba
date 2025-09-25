import os
from flask import Flask, request, session
from flask_cors import CORS
from dotenv import load_dotenv
from flask_restx import Api, Resource, fields, reqparse
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


# LangChain/LangGraph imports
from langchain_core.messages import HumanMessage

# --- IMPORTANT ---
# On importe directement le 'graph' depuis le module agent que vous avez fourni.
# Python va le trouver grâce à la structure de dossier src/agent.
from src.agent import graph

# --- NOUVEAUX IMPORTS DU PROJET GEO-OCR ---
from src.ocr_couche_superposition.ocr_processor import GeoOCRProcessor # Notre classe OCR isolée
from src.ocr_couche_superposition.layer_manager import layer_manager # L'instance déjà créée


# Charger les variables d'environnement depuis le fichier .env
# Assurez-vous que votre GEMINI_API_KEY est dans ce fichier
load_dotenv()

# Initialiser l'application Flask
app = Flask(__name__)
# Une clé secrète est OBLIGATOIRE pour utiliser la session Flask
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-tres-difficile-a-deviner')
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
CORS(app)

# --- INITIALISATION DES SERVICES ---
ocr_processor = GeoOCRProcessor()

# Initialiser Flask-RESTX pour l'API et la documentation Swagger
api = Api(app, version='1.0', title='API Agent LangGraph',
 description='Une API unifiée pour l\'agent conversationnel et le traitement de données géographiques.',
         doc='/doc/' # URL pour l'interface Swagger UI
)

# Namespace pour organiser les endpoints
chat_ns = api.namespace('chat', description='Opérations de l\'agent')

# Définir le modèle de données pour la requête (ce que l'API attend en entrée)
message_model = api.model('Message', {
    'message': fields.String(required=True, description='La question de l\'utilisateur pour l\'agent'),
    # On pourrait ajouter ici d'autres champs de configuration si besoin
    # 'config': fields.Nested(api.model('Config', { 'max_loops': fields.Integer }))
})

# Définir le modèle de données pour la réponse
reply_model = api.model('Reply', {
    'reply': fields.String(description='La réponse finale générée par l\'agent')
})

@chat_ns.route('/')
class AgentExecutor(Resource):
    @chat_ns.doc('execute_agent_graph')
    @chat_ns.expect(message_model)
    @chat_ns.marshal_with(reply_model)
    def post(self):
        """
        Exécute le graphe de l'agent avec la question de l'utilisateur et retourne la réponse finale.
        """
        data = api.payload
        user_message = data['message']
        print(f"Requête reçue pour l'agent : '{user_message}'")

        try:
            initial_state = {
                "messages": [HumanMessage(content=user_message)]
            }

            # --- DÉBUT DE LA MODIFICATION ---

            # On définit une configuration "rapide" pour l'exécution
            config = {
                "recursion_limit": 5, # Limite de sécurité
                "configurable": {
                    # On force l'agent à ne générer qu'UNE seule requête de recherche.
                    "number_of_initial_queries": 1,
                    
                    # On force l'agent à ne faire qu'UNE seule boucle (pas de réflexion supplémentaire).
                    "max_research_loops": 1,
                    
                    # On utilise un modèle "Flash" plus rapide pour la réponse finale.
                    "answer_model": "gemini-2.5-flash"
                }
            }

            # On invoque le graphe avec cette nouvelle configuration
            final_state = graph.invoke(initial_state, config=config)

            # --- FIN DE LA MODIFICATION ---

            if final_state and "messages" in final_state and final_state["messages"]:
                ai_response = final_state["messages"][-1].content
                print("Réponse de l'agent extraite avec succès.")
            else:
                ai_response = "Désolé, l'agent n'a pas pu générer une réponse."
                print("AVERTISSEMENT : L'état final de l'agent est inattendu.")

            return {'reply': ai_response}

        except Exception as e:
            print(f"ERREUR : Une erreur est survenue lors de l'exécution du graphe : {e}")
            api.abort(500, f"Erreur interne du serveur lors de l'exécution de l'agent : {e}")


# ==============================================================================
# NAMESPACE 2: OCR GÉOGRAPHIQUE (NOUVEAU)
# ==============================================================================
ocr_ns = api.namespace('ocr', description='Traitement OCR d\'images géographiques')

# Parser pour l'upload de fichiers dans Swagger
upload_parser = reqparse.RequestParser()
upload_parser.add_argument('file', location='files', type=FileStorage, required=True, help='Image de la levée géographique')

@ocr_ns.route('/process')
class OcrProcess(Resource):
    @ocr_ns.doc('process_image')
    @ocr_ns.expect(upload_parser)
    def post(self):
        """Uploade et traite une image pour en extraire des données GeoJSON."""
        args = upload_parser.parse_args()
        file = args['file']
        
        if file.filename == '':
            api.abort(400, "Aucun fichier sélectionné")

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            result = ocr_processor.extract_geographic_data(filepath)
            if not result['success']:
                api.abort(500, result['error'])

            geojson_data = ocr_processor.convert_to_geojson(result['data'])
            session['last_geojson'] = geojson_data # Stocke le résultat en session
            
            return {
                'success': True,
                'filename': filename,
                'geojson': geojson_data
            }, 200
        except Exception as e:
            api.abort(500, f"Erreur interne : {e}")
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

@ocr_ns.route('/last-data')
class OcrLastData(Resource):
    @ocr_ns.doc('get_last_ocr_data')
    def get(self):
        """Récupère les dernières données GeoJSON générées par l'OCR."""
        if 'last_geojson' in session:
            return session['last_geojson']
        return {'message': 'Aucune donnée en session. Veuillez d\'abord traiter une image.'}, 404


# ==============================================================================
# NAMESPACE 3: COUCHES GÉOGRAPHIQUES (NOUVEAU)
# ==============================================================================
layers_ns = api.namespace('layers', description='Gestion des couches de données GeoJSON')

@layers_ns.route('/info')
class LayersInfo(Resource):
    @layers_ns.doc('get_all_layers_info')
    def get(self):
        """Récupère les métadonnées de toutes les couches disponibles."""
        return layer_manager.get_layers_summary()

# Parser pour les requêtes de parcelles par localisation
parcelles_parser = reqparse.RequestParser()
parcelles_parser.add_argument('lat', type=float, required=True, help='Latitude du centre de la recherche')
parcelles_parser.add_argument('lon', type=float, required=True, help='Longitude du centre de la recherche')
parcelles_parser.add_argument('radius', type=int, default=1000, help='Rayon de recherche en mètres')

@layers_ns.route('/data/<string:layer_key>')
class LayerData(Resource):
    @layers_ns.doc('get_layer_data_by_key', params={'layer_key': 'La clé de la couche (ex: aif, litige, parcelles)'})
    @layers_ns.expect(parcelles_parser) # Swagger montrera les params pour 'parcelles'
    def get(self, layer_key):
        """Récupère les données GeoJSON pour une couche spécifique.
           Pour 'parcelles', les paramètres lat, lon et radius sont requis."""
        if layer_key == 'parcelles':
            args = parcelles_parser.parse_args()
            data = layer_manager.load_parcelles_by_location(args['lat'], args['lon'], args['radius'])
            if data is None:
                api.abort(404, "Impossible de charger les parcelles pour cette localisation.")
            return data
        
        data = layer_manager.get_layer(layer_key)
        if data is None:
            api.abort(404, f"Couche '{layer_key}' non trouvée.")
        return data

# Modèle pour la vérification de chevauchement
geojson_model = api.model('GeoJSONFeature', {}) # Modèle générique pour le GeoJSON

@layers_ns.route('/check-overlaps')
class CheckOverlaps(Resource):
    @layers_ns.doc('check_feature_overlaps')
    @layers_ns.expect(geojson_model)
    def post(self):
        """Vérifie les chevauchements entre un GeoJSON de parcelle fourni et les couches de données."""
        parcel_geojson = request.get_json()
        if not parcel_geojson:
            api.abort(400, "Corps de la requête GeoJSON manquant.")
        
        try:
            overlaps = layer_manager.check_overlaps(parcel_geojson)
            return {
                'success': True,
                'overlaps': overlaps
            }
        except Exception as e:
            api.abort(500, f"Erreur lors de la vérification des chevauchements : {e}")



if __name__ == '__main__':
    # Nous utilisons le port 5001 pour éviter les conflits
    app.run(host='0.0.0.0', port=5001, debug=True)