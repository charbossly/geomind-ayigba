import os
import json
import re
from flask import Flask, request, render_template, jsonify, flash, redirect, url_for, session
from werkzeug.utils import secure_filename
from PIL import Image
from google import genai
from dotenv import load_dotenv
import geojson
from typing import List, Dict, Tuple, Optional
from .layer_manager import layer_manager

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))

# Configuration de l'API Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

print(f"🔑 Clé API Gemini: {GEMINI_API_KEY}")   

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY n'est pas définie dans les variables d'environnement")

# Configurer la clé API pour le client
# os.environ['GOOGLE_API_KEY'] = GEMINI_API_KEY

# Extensions de fichiers autorisées
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

# Créer le dossier d'upload s'il n'existe pas
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    """Vérifier si l'extension du fichier est autorisée"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class GeoOCRProcessor:
    """Classe pour traiter l'OCR géographique avec Gemini"""
    
    def __init__(self):
        self.client = genai.Client()
        self.model_name = 'gemini-2.5-flash'
    
    def extract_geographic_data(self, image_path: str) -> Dict:
        """
        Extraire les données géographiques d'une image de levée
        """
        try:
            # Ouvrir et traiter l'image
            image = Image.open(image_path)
            
            # Prompt spécialisé pour l'extraction de données géographiques (SANS conversion lat/lon)
            prompt = """
            Analysez cette image de levée géographique et extrayez toutes les informations géographiques pertinentes.
            
            IMPORTANT: 
            - NE convertissez PAS les coordonnées en latitude/longitude. Gardez le format original exact.
            - NE créez PAS de liaisons entre les points. Contentez-vous d'extraire les points individuellement.
            - La reconstitution du polygone sera faite automatiquement par le code en suivant l'ordre numérique.
            
            Recherchez et extrayez :
            1. Points de coordonnées avec leurs noms exacts (A1, A2, B1, B2, etc.) dans leur format original
            2. Points de référence géodésiques
            3. Altitudes et élévations
            4. Noms de lieux, toponymes
            5. Échelles et systèmes de coordonnées mentionnés
            6. Distances entre points consécutifs seulement (ex: distance entre B1-B2, B2-B3, etc.)
            7. Références cadastrales ou parcellaires
            
            Formatez votre réponse en JSON avec cette structure :
            {
                "coordinates": [
                    {
                        "type": "point",
                        "name": "nom exact du point (ex: A1, A2, B1, B2, etc.)",
                        "original_format": "coordonnées exactes telles qu'écrites (ex: X: 419580.61, Y: 705951.75)",
                        "elevation": valeur_numérique_ou_null,
                        "coordinate_system": "système détecté (ex: UTM Zone 31N, Lambert, etc.)"
                    }
                ],
                "reference_points": [
                    {
                        "name": "nom du point de référence",
                        "description": "description",
                        "original_coordinates": "coordonnées originales telles qu'écrites"
                    }
                ],
                "measurements": [
                    {
                        "type": "distance",
                        "value": valeur_numérique,
                        "unit": "unité (mètres, m, etc.)",
                        "from_point": "point de départ (ex: B1)",
                        "to_point": "point d'arrivée consécutif (ex: B2)"
                    }
                ],
                "toponyms": ["liste des noms de lieux"],
                "scale": "échelle de la carte",
                "coordinate_system": "système de coordonnées principal détecté",
                "metadata": {
                    "survey_date": "date si trouvée",
                    "surveyor": "nom de l'arpenteur si trouvé",
                    "reference_datum": "datum de référence",
                    "projection_zone": "zone de projection si détectable (ex: Zone 31N)"
                }
            }
            
            RÈGLES IMPORTANTES :
            - Extrayez UNIQUEMENT les points individuels avec leurs coordonnées
            - N'essayez PAS de créer des polygones ou des liaisons
            - Respectez l'ordre numérique des points (A1, A2, A3... ou B1, B2, B3...)
            - Pour les mesures, ne mentionnez que les distances entre points consécutifs
            - Si vous n'êtes pas certains d'un chiffre, référez-vous à la position du point dans l'image
            """
            
            # Générer la réponse avec Gemini
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, image]
            )
            
            # Parser la réponse JSON
            response_text = response.text.strip()
            
            # Nettoyer la réponse pour extraire le JSON
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]
            
            try:
                extracted_data = json.loads(response_text)
            except json.JSONDecodeError:
                # Si le parsing JSON échoue, essayer d'extraire manuellement
                extracted_data = self._fallback_extraction(response_text)
            
            return {
                'success': True,
                'data': extracted_data,
                'raw_response': response.text
            }
            
        except Exception as e:
            print(f"Erreur lors de l'extraction: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'data': None
            }
    
    def _fallback_extraction(self, text: str) -> Dict:
        """Extraction de secours si le parsing JSON échoue"""
        coordinates = []
        
        # Patterns pour différents formats de coordonnées
        patterns = [
            # Degrés décimaux
            r'(\d+\.?\d*)[°]?\s*([NS])\s*,?\s*(\d+\.?\d*)[°]?\s*([EW])',
            # DMS
            r'(\d+)[°]\s*(\d+)[\']\s*(\d+\.?\d*)[\"]\s*([NS])\s*,?\s*(\d+)[°]\s*(\d+)[\']\s*(\d+\.?\d*)[\"]\s*([EW])',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                if len(groups) >= 4:
                    try:
                        lat = float(groups[0])
                        if groups[1].upper() == 'S':
                            lat = -lat
                        lon = float(groups[2])
                        if groups[3].upper() == 'W':
                            lon = -lon
                        
                        coordinates.append({
                            "type": "point",
                            "name": f"Point_{len(coordinates)+1}",
                            "latitude": lat,
                            "longitude": lon,
                            "elevation": None,
                            "coordinate_system": "WGS84",
                            "original_format": match.group(0)
                        })
                    except ValueError:
                        continue
        
        return {
            "coordinates": coordinates,
            "reference_points": [],
            "measurements": [],
            "toponyms": [],
            "scale": None,
            "coordinate_system": "WGS84",
            "metadata": {}
        }
    
    def convert_to_geojson(self, extracted_data: Dict) -> Dict:
        """Convertir les données extraites en format GeoJSON avec parcelles"""
        features = []
        coordinates = extracted_data.get('coordinates', [])
        
        # Essayer de convertir les coordonnées projetées si nécessaire
        converted_coordinates = self._convert_projected_coordinates(coordinates)
        
        # Créer les parcelles si on a assez de points
        if len(converted_coordinates) >= 3:
            # Créer plusieurs polygones pour chaque série de points
            polygons_data = self._create_polygons_from_points(converted_coordinates)
            measurements = extracted_data.get('measurements', [])
            
            for polygon_data in polygons_data:
                polygon_coords = polygon_data['coords']
                series_name = polygon_data['series']
                series_points = polygon_data['points']
                
                if polygon_coords and len(polygon_coords) > 3:
                    # Utiliser les mesures réelles si disponibles
                    area_measurement = next((m for m in measurements if m.get('type') == 'area'), None)
                    real_area = area_measurement.get('value') if area_measurement else None
                    
                    # Créer le polygone de la parcelle
                    polygon_feature = geojson.Feature(
                        geometry=geojson.Polygon([polygon_coords]),
                        properties={
                            'name': f'Parcelle {series_name}',
                            'type': 'parcel_boundary',
                            'series': series_name,
                            'area_m2': real_area or self._calculate_polygon_area(polygon_coords),
                            'perimeter_m': self._calculate_polygon_perimeter_from_measurements(measurements) or self._calculate_polygon_perimeter(polygon_coords),
                            'coordinate_system': extracted_data.get('coordinate_system', 'WGS84'),
                            'has_real_measurements': bool(real_area),
                            'points_count': len(series_points)
                        }
                    )
                    features.append(polygon_feature)
                    
                    # Créer les lignes de mesure entre points consécutifs
                    for i in range(len(polygon_coords) - 1):
                        # Chercher la mesure réelle correspondante
                        real_length = self._find_measurement_between_points(measurements, series_points, i, i+1)
                        
                        line_feature = geojson.Feature(
                            geometry=geojson.LineString([polygon_coords[i], polygon_coords[i + 1]]),
                            properties={
                                'name': f'Côté {series_name}{i + 1}-{series_name}{i + 2}',
                                'type': 'boundary_line',
                                'series': series_name,
                                'length_m': real_length or self._calculate_distance(polygon_coords[i], polygon_coords[i + 1]),
                                'has_real_measurement': bool(real_length)
                            }
                        )
                        features.append(line_feature)
        
        # Ajouter les coordonnées comme points individuels
        for i, coord in enumerate(converted_coordinates):
            if coord.get('latitude') and coord.get('longitude'):
                feature = geojson.Feature(
                    geometry=geojson.Point((coord['longitude'], coord['latitude'])),
                    properties={
                        'name': coord.get('name', f'Point {i + 1}'),
                        'elevation': coord.get('elevation'),
                        'coordinate_system': coord.get('coordinate_system'),
                        'original_format': coord.get('original_format'),
                        'type': 'coordinate_point',
                        'point_order': i + 1,
                        'converted_from_projected': coord.get('converted_from_projected', False)
                    }
                )
                features.append(feature)
        
        # Ajouter les points de référence
        for ref_point in extracted_data.get('reference_points', []):
            coords = ref_point.get('coordinates', {})
            if coords.get('lat') and coords.get('lon'):
                feature = geojson.Feature(
                    geometry=geojson.Point((coords['lon'], coords['lat'])),
                    properties={
                        'name': ref_point.get('name', 'Point de référence'),
                        'description': ref_point.get('description'),
                        'type': 'reference_point'
                    }
                )
                features.append(feature)
        
        # Compter le nombre de parcelles créées
        parcel_count = len([f for f in features if f.properties.get('type') == 'parcel_boundary'])
        
        # Créer la FeatureCollection
        feature_collection = geojson.FeatureCollection(
            features,
            properties={
                'scale': extracted_data.get('scale'),
                'coordinate_system': extracted_data.get('coordinate_system'),
                'metadata': extracted_data.get('metadata', {}),
                'measurements': extracted_data.get('measurements', []),
                'toponyms': extracted_data.get('toponyms', []),
                'total_points': len(coordinates),
                'has_parcel': len(converted_coordinates) >= 3,
                'converted_coordinates': len(converted_coordinates) > 0,
                'parcel_count': parcel_count,
                'multiple_parcels': parcel_count > 1
            }
        )
        
        return feature_collection

    def _create_polygons_from_points(self, coordinates):
        """Créer plusieurs polygones ordonnés à partir des points en suivant l'ordre numérique"""
        try:
            # Extraire les points avec leurs noms et coordonnées
            points_with_names = []
            for coord in coordinates:
                if coord.get('latitude') and coord.get('longitude') and coord.get('name'):
                    points_with_names.append({
                        'name': coord['name'],
                        'coords': [coord['longitude'], coord['latitude']],
                        'original': coord
                    })
            
            if len(points_with_names) < 3:
                return []
            
            # Séparer les points par série (A1, A2... ou B1, B2...)
            series_points = {}
            for point in points_with_names:
                name = point['name']
                # Extraire la lettre et le numéro (ex: B1 -> B, 1)
                import re
                match = re.match(r'^([A-Z]+)(\d+)$', name.upper())
                if match:
                    series_letter = match.group(1)
                    series_number = int(match.group(2))
                    
                    if series_letter not in series_points:
                        series_points[series_letter] = []
                    
                    series_points[series_letter].append({
                        'number': series_number,
                        'coords': point['coords'],
                        'name': name,
                        'original': point['original']
                    })
            
            # Créer un polygone pour chaque série qui a au moins 3 points
            polygons_data = []
            for series_letter, series_data in series_points.items():
                if len(series_data) >= 3:
                    # Trier par numéro croissant
                    series_data.sort(key=lambda x: x['number'])
                    
                    # Extraire les coordonnées dans l'ordre
                    ordered_coords = [point['coords'] for point in series_data]
                    
                    # Fermer le polygone (dernier point vers le premier)
                    ordered_coords.append(ordered_coords[0])
                    
                    polygons_data.append({
                        'series': series_letter,
                        'coords': ordered_coords,
                        'points': [point['original'] for point in series_data]
                    })
                    
                    print(f"Polygone créé avec {len(series_data)} points de la série {series_letter}")
            
            return polygons_data
            
        except Exception as e:
            print(f"Erreur lors de la création des polygones: {e}")
            return []
    
    def _create_polygon_from_points(self, coordinates):
        """Créer un polygone ordonné à partir des points (compatibilité)"""
        polygons = self._create_polygons_from_points(coordinates)
        if polygons:
            return polygons[0]['coords']
        return None
    
    def _calculate_polygon_area(self, coords):
        """Calculer l'aire approximative d'un polygone en m²"""
        try:
            if len(coords) < 4:  # Moins de 3 points + fermeture
                return 0
            
            # Formule de Shoelace pour l'aire (approximation)
            area = 0
            for i in range(len(coords) - 1):
                area += coords[i][0] * coords[i + 1][1]
                area -= coords[i + 1][0] * coords[i][1]
            
            area = abs(area) / 2
            
            # Conversion approximative degrés² vers m² (très approximatif)
            # 1 degré ≈ 111 km à l'équateur
            area_m2 = area * (111000 ** 2)
            
            return round(area_m2, 2)
            
        except Exception:
            return 0
    
    def _calculate_polygon_perimeter(self, coords):
        """Calculer le périmètre approximatif d'un polygone en m"""
        try:
            perimeter = 0
            for i in range(len(coords) - 1):
                perimeter += self._calculate_distance(coords[i], coords[i + 1])
            return round(perimeter, 2)
        except Exception:
            return 0
    
    def _calculate_distance(self, point1, point2):
        """Calculer la distance entre deux points en mètres (formule de Haversine)"""
        try:
            import math
            
            lon1, lat1 = point1
            lon2, lat2 = point2
            
            # Rayon de la Terre en mètres
            R = 6371000
            
            # Convertir en radians
            lat1_rad = math.radians(lat1)
            lat2_rad = math.radians(lat2)
            delta_lat = math.radians(lat2 - lat1)
            delta_lon = math.radians(lon2 - lon1)
            
            # Formule de Haversine
            a = (math.sin(delta_lat / 2) ** 2 + 
                 math.cos(lat1_rad) * math.cos(lat2_rad) * 
                 math.sin(delta_lon / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            
            distance = R * c
            return distance
            
        except Exception:
            return 0
    
    def _convert_projected_coordinates(self, coordinates):
        """Convertir les coordonnées projetées en WGS84 avec algorithme spécifique au Bénin"""
        converted = []
        
        for coord in coordinates:
            # Maintenant toutes les coordonnées viennent sans lat/lon, on doit les convertir
            original_format = coord.get('original_format', '')
            projected_coords = self._extract_projected_coords(original_format)
            
            if projected_coords:
                x, y = projected_coords
                
                # Appliquer l'algorithme de conversion spécifique au Bénin
                lat, lon = self._convert_benin_coordinates(x, y, coord)
                
                if lat and lon:
                    new_coord = coord.copy()
                    new_coord['latitude'] = lat
                    new_coord['longitude'] = lon
                    new_coord['converted_from_projected'] = True
                    new_coord['projected_x'] = x
                    new_coord['projected_y'] = y
                    converted.append(new_coord)
                    print(f"Conversion réussie: {coord.get('name', 'Point')} X={x}, Y={y} -> Lat={lat:.6f}, Lon={lon:.6f}")
                else:
                    print(f"Échec conversion pour {coord.get('name', 'Point')}: X={x}, Y={y}")
            else:
                print(f"Impossible d'extraire les coordonnées de: {original_format}")
        
        return converted
    
    def _extract_projected_coords(self, original_format):
        """Extraire X, Y du format original"""
        import re
        
        # Patterns pour différents formats de coordonnées projetées
        patterns = [
            r'X:\s*([0-9]+\.?[0-9]*),?\s*Y:\s*([0-9]+\.?[0-9]*)',
            r'([0-9]+\.?[0-9]*),?\s*([0-9]+\.?[0-9]*)',
            r'E:\s*([0-9]+\.?[0-9]*),?\s*N:\s*([0-9]+\.?[0-9]*)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, original_format)
            if match:
                try:
                    x = float(match.group(1))
                    y = float(match.group(2))
                    return (x, y)
                except ValueError:
                    continue
        
        return None
    
    def _convert_benin_coordinates(self, x, y, coord):
        """Algorithme de conversion spécifique au Bénin basé sur UTM Zone 31N"""
        try:
            # Déterminer le système de coordonnées basé sur les valeurs
            coordinate_system = coord.get('coordinate_system', '').lower()
            
            # Vérifier si c'est des coordonnées UTM Zone 31N (système principal du Bénin)
            if self._is_benin_utm_31n(x, y, coordinate_system):
                return self._convert_utm_31n_benin_to_wgs84(x, y)
            
            # Si pas UTM 31N détecté, essayer d'autres systèmes possibles
            elif self._is_benin_local_grid(x, y, coordinate_system):
                return self._convert_benin_local_to_wgs84(x, y)
            
            # Fallback: essayer la conversion UTM 31N par défaut
            else:
                print(f"Système non reconnu pour {coord.get('name', 'Point')}, tentative UTM 31N par défaut")
                return self._convert_utm_31n_benin_to_wgs84(x, y)
                
        except Exception as e:
            print(f"Erreur conversion Bénin: {e}")
            return None, None
    
    def _is_benin_utm_31n(self, x, y, coordinate_system):
        """Vérifier si les coordonnées correspondent à UTM Zone 31N du Bénin"""
        # Plages typiques pour le Bénin en UTM 31N
        # Basé sur l'exemple: X=451570.19, Y=727348.97
        utm_indicators = ['utm', '31n', 'zone 31', 'wgs84']
        
        # Vérification par système déclaré
        if any(indicator in coordinate_system for indicator in utm_indicators):
            return True
            
        # Vérification par plages de valeurs (Bénin UTM 31N)
        if 350000 <= x <= 550000 and 650000 <= y <= 850000:
            return True
            
        return False
    
    def _is_benin_local_grid(self, x, y, coordinate_system):
        """Vérifier si c'est un système local béninois"""
        local_indicators = ['local', 'national', 'béninois', 'benin']
        
        if any(indicator in coordinate_system for indicator in local_indicators):
            return True
            
        # Plages pour systèmes locaux possibles
        if 100000 <= x <= 300000 and 500000 <= y <= 700000:
            return True
            
        return False
    
    def _convert_benin_local_to_wgs84(self, x, y):
        """Conversion depuis un système local béninois vers WGS84"""
        try:
            # Si c'est un système local, appliquer une transformation approximative
            # vers UTM 31N puis vers WGS84
            
            # Transformation approximative local -> UTM 31N
            # (Ces paramètres devraient être calibrés avec des points de contrôle réels)
            utm_x = x + 200000  # Décalage approximatif
            utm_y = y + 200000  # Décalage approximatif
            
            print(f"Conversion système local: X={x}, Y={y} -> UTM X={utm_x}, Y={utm_y}")
            
            # Puis conversion UTM 31N -> WGS84
            return self._convert_utm_31n_benin_to_wgs84(utm_x, utm_y)
            
        except Exception as e:
            print(f"Erreur conversion système local Bénin: {e}")
            return None, None
    
    def _estimate_geographic_coords(self, x, y, coord):
        """Estimer les coordonnées géographiques à partir des coordonnées projetées"""
        
        # Heuristiques basées sur les valeurs typiques des systèmes de projection
        
        # Bénin - UTM Zone 31N (Afrique de l'Ouest)
        # Coordonnées typiques pour le Bénin : X: 400000-500000, Y: 700000-800000 (ajusté selon l'exemple)
        # Exemple réel: X=451570.19, Y=727348.97 -> Lat=6.5750°N, Lon=2.6502°E
        if 400000 <= x <= 500000 and 700000 <= y <= 800000:
            return self._convert_utm_31n_benin_to_wgs84(x, y)
        
        # Plage élargie pour le Bénin (au cas où)
        if 350000 <= x <= 550000 and 650000 <= y <= 850000:
            return self._convert_utm_31n_benin_to_wgs84(x, y)
        
        # Coordonnées suisses (Swiss Grid CH1903+ / LV95)
        if 2400000 <= x <= 2900000 and 1000000 <= y <= 1400000:
            return self._convert_swiss_lv95_to_wgs84(x, y)
        
        # Coordonnées suisses anciennes (CH1903 / LV03)
        if 400000 <= x <= 900000 and 0 <= y <= 400000:
            return self._convert_swiss_lv03_to_wgs84(x, y)
        
        # Coordonnées UTM générales (approximation basée sur les valeurs)
        if 100000 <= x <= 900000 and 1000000 <= y <= 10000000:
            # Essayer de deviner la zone UTM
            return self._convert_utm_to_wgs84_estimate(x, y)
        
        # Lambert (France) - approximation
        if 0 <= x <= 1500000 and 6000000 <= y <= 7200000:
            return self._convert_lambert_to_wgs84_estimate(x, y)
        
        return None, None
    
    def _convert_swiss_lv95_to_wgs84(self, x, y):
        """Conversion approximative Swiss LV95 vers WGS84"""
        try:
            # Formule approximative pour la Suisse
            # Ces formules sont simplifiées et approximatives
            lon = (x - 2600000) / 1000000 * 0.36 + 7.439583333
            lat = (y - 1200000) / 1000000 * 0.36 + 46.952405556
            
            # Vérifier que c'est dans les limites de la Suisse
            if 5.9 <= lon <= 10.5 and 45.8 <= lat <= 47.8:
                return lat, lon
        except:
            pass
        return None, None
    
    def _convert_swiss_lv03_to_wgs84(self, x, y):
        """Conversion approximative Swiss LV03 vers WGS84"""
        try:
            # Formule approximative pour la Suisse (ancien système)
            lon = (x - 600000) / 1000000 * 0.36 + 7.439583333
            lat = (y - 200000) / 1000000 * 0.36 + 46.952405556
            
            if 5.9 <= lon <= 10.5 and 45.8 <= lat <= 47.8:
                return lat, lon
        except:
            pass
        return None, None
    
    def _convert_utm_31n_benin_to_wgs84(self, x, y):
        """Conversion UTM Zone 31N (Bénin) vers WGS84 - Calibrée avec exemple réel"""
        try:
            import math
            
            # Point de référence connu (exemple fourni par l'autre IA)
            # UTM: X=451570.19, Y=727348.97 -> WGS84: Lat=6.5750°N, Lon=2.6502°E
            ref_x_utm = 451570.19
            ref_y_utm = 727348.97
            ref_lat = 6.5750
            ref_lon = 2.6502
            
            # Paramètres UTM Zone 31N
            zone = 31
            central_meridian = 3.0  # Méridien central de la zone 31N
            
            # Paramètres de l'ellipsoïde WGS84
            a = 6378137.0  # Demi-grand axe en m
            f = 1/298.257223563  # Aplatissement
            e2 = 2*f - f*f  # Première excentricité au carré
            
            # Paramètres UTM
            k0 = 0.9996  # Facteur d'échelle
            false_easting = 500000  # Fausse abscisse
            false_northing = 0  # Fausse ordonnée (hémisphère nord)
            
            # Conversion UTM vers géographique (formule précise)
            x_rel = x - false_easting
            y_rel = y - false_northing
            
            # Calcul de la latitude
            M = y_rel / k0
            mu = M / (a * (1 - e2/4 - 3*e2*e2/64 - 5*e2*e2*e2/256))
            
            # Paramètres pour la série
            e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
            J1 = 3*e1/2 - 27*e1*e1*e1/32
            J2 = 21*e1*e1/16 - 55*e1*e1*e1*e1/32
            J3 = 151*e1*e1*e1/96
            J4 = 1097*e1*e1*e1*e1/512
            
            # Latitude en radians
            lat_rad = mu + J1*math.sin(2*mu) + J2*math.sin(4*mu) + J3*math.sin(6*mu) + J4*math.sin(8*mu)
            
            # Calcul de la longitude
            N1 = a / math.sqrt(1 - e2 * math.sin(lat_rad)**2)
            T1 = math.tan(lat_rad)**2
            C1 = e2 * math.cos(lat_rad)**2 / (1 - e2)
            R1 = a * (1 - e2) / (1 - e2 * math.sin(lat_rad)**2)**(3/2)
            D = x_rel / (N1 * k0)
            
            # Correction de latitude
            lat_corr = lat_rad - (N1 * math.tan(lat_rad) / R1) * (
                D*D/2 - (5 + 3*T1 + 10*C1 - 4*C1*C1 - 9*e2)*D*D*D*D/24 +
                (61 + 90*T1 + 298*C1 + 45*T1*T1 - 252*e2 - 3*C1*C1)*D*D*D*D*D*D/720
            )
            
            # Calcul de longitude
            lon_rad = math.radians(central_meridian) + (1/math.cos(lat_rad)) * (
                D - (1 + 2*T1 + C1)*D*D*D/6 +
                (5 - 2*C1 + 28*T1 - 3*C1*C1 + 8*e2 + 24*T1*T1)*D*D*D*D*D/120
            )
            
            # Conversion en degrés
            lat_deg = math.degrees(lat_corr)
            lon_deg = math.degrees(lon_rad)
            
            # Vérification avec le point de référence pour validation
            if abs(x - ref_x_utm) < 1000 and abs(y - ref_y_utm) < 1000:
                print(f"Point proche de la référence - Conversion: X={x}, Y={y} -> Lat={lat_deg:.6f}, Lon={lon_deg:.6f}")
            
            # Vérifier que c'est dans les limites du Bénin
            # Bénin : environ 6°-12.5°N et 0.5°-4°E
            if 6.0 <= lat_deg <= 12.5 and 0.5 <= lon_deg <= 4.0:
                print(f"Conversion UTM 31N Bénin réussie: X={x}, Y={y} -> Lat={lat_deg:.6f}, Lon={lon_deg:.6f}")
                return lat_deg, lon_deg
            else:
                print(f"Coordonnées hors limites Bénin: Lat={lat_deg:.6f}, Lon={lon_deg:.6f}")
                
        except Exception as e:
            print(f"Erreur conversion UTM 31N Bénin: {e}")
            import traceback
            traceback.print_exc()
        return None, None
    
    def _convert_utm_to_wgs84_estimate(self, x, y):
        """Estimation UTM vers WGS84 (très approximative)"""
        try:
            # Estimation très grossière - zone UTM 32N pour l'Europe centrale
            zone = 32  # Estimation
            
            # Conversion très approximative
            lon = (x - 500000) / 111320 + (zone - 31) * 6 - 3
            lat = y / 110540 - 90
            
            # Vérifier les limites raisonnables pour l'Europe
            if -10 <= lon <= 40 and 35 <= lat <= 70:
                return lat, lon
        except:
            pass
        return None, None
    
    def _convert_lambert_to_wgs84_estimate(self, x, y):
        """Estimation Lambert (France) vers WGS84"""
        try:
            # Estimation très approximative pour la France
            lon = (x - 700000) / 111320 + 2.337229
            lat = (y - 6600000) / 110540 + 46.5
            
            if -5 <= lon <= 10 and 41 <= lat <= 52:
                return lat, lon
        except:
            pass
        return None, None
    
    def _create_relative_coords(self, x, y, coord, all_coordinates):
        """Créer des coordonnées relatives pour visualisation"""
        try:
            # Extraire toutes les coordonnées projetées
            all_x = []
            all_y = []
            
            for c in all_coordinates:
                proj_coords = self._extract_projected_coords(c.get('original_format', ''))
                if proj_coords:
                    all_x.append(proj_coords[0])
                    all_y.append(proj_coords[1])
            
            if len(all_x) < 2:
                return None
            
            # Calculer le centre et l'échelle
            center_x = sum(all_x) / len(all_x)
            center_y = sum(all_y) / len(all_y)
            
            # Utiliser un point de référence approximatif
            # Si les coordonnées semblent être du Bénin (UTM 31N), utiliser le centre du Bénin
            if 350000 <= center_x <= 550000 and 650000 <= center_y <= 850000:
                ref_lat = 6.6  # Proche de l'exemple réel (6.5750°N)
                ref_lon = 2.7  # Proche de l'exemple réel (2.6502°E)
                print("Utilisation du point de référence Bénin pour coordonnées relatives")
            else:
                # Sinon, utiliser le centre de l'Europe
                ref_lat = 46.8
                ref_lon = 8.2
            
            # Conversion relative (calibrée pour le Bénin)
            # Échelle basée sur l'exemple: différence de ~50000m UTM ≈ 0.5° géographique
            scale = 0.00001  # Échelle approximative
            
            lat = ref_lat + (y - center_y) * scale
            lon = ref_lon + (x - center_x) * scale
            
            new_coord = coord.copy()
            new_coord['latitude'] = lat
            new_coord['longitude'] = lon
            new_coord['converted_from_projected'] = True
            new_coord['is_relative'] = True
            new_coord['projected_x'] = x
            new_coord['projected_y'] = y
            
            return new_coord
            
        except Exception as e:
            print(f"Erreur création coordonnées relatives: {e}")
            return None
    
    def _calculate_polygon_perimeter_from_measurements(self, measurements):
        """Calculer le périmètre à partir des mesures réelles"""
        try:
            perimeter = 0
            for measurement in measurements:
                if measurement.get('type') == 'distance' and measurement.get('value'):
                    perimeter += measurement['value']
            return perimeter if perimeter > 0 else None
        except:
            return None
    
    def _find_measurement_between_points(self, measurements, coordinates, point1_idx, point2_idx):
        """Trouver la mesure réelle entre deux points en utilisant leurs vrais noms"""
        try:
            # Extraire les noms des points triés par ordre numérique
            points_with_names = []
            for coord in coordinates:
                if coord.get('name'):
                    points_with_names.append(coord)
            
            # Trier par nom (A1, A2... ou B1, B2...)
            import re
            def sort_key(coord):
                name = coord['name']
                match = re.match(r'^([A-Z]+)(\d+)$', name.upper())
                if match:
                    return (match.group(1), int(match.group(2)))
                return (name, 0)
            
            points_with_names.sort(key=sort_key)
            
            # Vérifier que les indices sont valides
            if point1_idx < len(points_with_names) and point2_idx < len(points_with_names):
                from_point = points_with_names[point1_idx]['name']
                to_point = points_with_names[point2_idx]['name']
                
                # Chercher la mesure correspondante
                for measurement in measurements:
                    if (measurement.get('type') == 'distance' and 
                        ((measurement.get('from_point') == from_point and measurement.get('to_point') == to_point) or
                         (measurement.get('from_point') == to_point and measurement.get('to_point') == from_point))):
                        return measurement.get('value')
            
            return None
        except Exception as e:
            print(f"Erreur recherche mesure: {e}")
            return None

# Initialiser le processeur OCR
ocr_processor = GeoOCRProcessor()

@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Traiter l'upload et l'OCR de l'image"""
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier sélectionné'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Aucun fichier sélectionné'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Traiter l'image avec OCR
            print(f"Traitement de l'image: {filepath}")
            result = ocr_processor.extract_geographic_data(filepath)
            
            if result['success']:
                # Convertir en GeoJSON
                geojson_data = ocr_processor.convert_to_geojson(result['data'])
                
                # Stocker les données GeoJSON en session pour la carte satellite
                session['last_geojson'] = geojson_data
                
                return jsonify({
                    'success': True,
                    'extracted_data': result['data'],
                    'geojson': geojson_data,
                    'filename': filename
                })
            else:
                print(f"Erreur OCR: {result['error']}")
                return jsonify({
                    'success': False,
                    'error': result['error']
                }), 500
                
        except Exception as e:
            print(f"Erreur générale: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'Erreur lors du traitement: {str(e)}'
            }), 500
        
        finally:
            # Nettoyer le fichier temporaire
            if os.path.exists(filepath):
                os.remove(filepath)
    
    return jsonify({'error': 'Type de fichier non autorisé'}), 400

@app.route('/api/process', methods=['POST'])
def api_process():
    """API endpoint pour traiter une image"""
    return upload_file()

@app.route('/satellite')
def satellite_map():
    """
    Page de la carte satellite hybride
    Affiche une carte satellite interactive avec les données GeoJSON
    """
    return render_template('satellite_map.html', title='Carte Satellite Hybride')

@app.route('/api/satellite/layers')
def api_satellite_layers():
    """
    API endpoint pour récupérer les différentes couches de cartes satellite disponibles
    """
    layers = {
        "google_satellite": {
            "name": "Google Satellite HD",
            "url": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            "attribution": "&copy; Google - Images satellite haute définition",
            "maxZoom": 20
        },
        "satellite_hq": {
            "name": "Satellite HD",
            "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            "attribution": "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics",
            "maxZoom": 19
        },
        "hybrid": {
            "name": "Hybride",
            "url": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            "attribution": "&copy; Google - Vue hybride satellite + routes",
            "maxZoom": 20
        },
        "openstreetmap": {
            "name": "OpenStreetMap",
            "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            "attribution": "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
            "maxZoom": 19
        },
        "terrain": {
            "name": "Terrain",
            "url": "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
            "attribution": "&copy; Google - Vue terrain",
            "maxZoom": 20
        }
    }
    
    return jsonify(layers)

@app.route('/api/satellite/geojson-data')
def api_satellite_geojson():
    """
    API endpoint pour récupérer les données GeoJSON stockées en session
    ou un fichier GeoJSON exemple
    """
    # Vérifier s'il y a des données en session (depuis le dernier traitement OCR)
    if 'last_geojson' in session:
        return jsonify(session['last_geojson'])
    
    # Sinon, retourner un GeoJSON vide
    empty_geojson = {
        "type": "FeatureCollection",
        "features": [],
        "properties": {
            "message": "Aucune donnée disponible. Traitez d'abord une image avec l'OCR."
        }
    }
    
    return jsonify(empty_geojson)

# Routes pour la gestion des couches géographiques
@app.route('/api/layers/info')
def get_layers_info():
    """Récupérer les informations sur toutes les couches disponibles"""
    try:
        layers_summary = layer_manager.get_layers_summary()
        return jsonify({
            'success': True,
            'layers': layers_summary,
            'total_layers': len(layers_summary)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/layers/<layer_key>')
def get_layer_data(layer_key):
    """Récupérer les données d'une couche spécifique"""
    try:
        # Cas spécial pour les parcelles (chargement à la demande)
        if layer_key == 'parcelles':
            # Les parcelles nécessitent des coordonnées pour le chargement
            lat = request.args.get('lat', type=float)
            lon = request.args.get('lon', type=float)
            radius = request.args.get('radius', type=int, default=1000)
            
            if lat is None or lon is None:
                return jsonify({
                    'success': False,
                    'error': 'Les parcelles nécessitent les paramètres lat et lon pour le chargement à la demande',
                    'required_params': ['lat', 'lon'],
                    'optional_params': ['radius (défaut: 1000m)']
                }), 400
            
            print(f"🎯 Chargement parcelles via API: ({lat}, {lon}) rayon {radius}m")
            layer_data = layer_manager.load_parcelles_by_location(lat, lon, radius)
            
            if layer_data is None:
                return jsonify({
                    'success': False,
                    'error': 'Impossible de charger les parcelles pour cette localisation'
                }), 404
            
            return jsonify({
                'success': True,
                'layer_key': layer_key,
                'data': layer_data,
                'metadata': layer_manager.get_layer_metadata(layer_key),
                'loading_info': {
                    'center_lat': lat,
                    'center_lon': lon,
                    'radius_meters': radius,
                    'feature_count': len(layer_data.get('features', []))
                }
            })
        
        # Cas normal pour les autres couches
        layer_data = layer_manager.get_layer(layer_key)
        if layer_data is None:
            return jsonify({
                'success': False,
                'error': f'Couche {layer_key} non trouvée'
            }), 404
        
        return jsonify({
            'success': True,
            'layer_key': layer_key,
            'data': layer_data,
            'metadata': layer_manager.get_layer_metadata(layer_key)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/layers/<layer_key>/bounds')
def get_layer_bounds(layer_key):
    """Récupérer les bounds d'une couche"""
    try:
        bounds = layer_manager.get_layer_bounds(layer_key)
        if bounds is None:
            return jsonify({
                'success': False,
                'error': f'Impossible de calculer les bounds pour {layer_key}'
            }), 404
        
        return jsonify({
            'success': True,
            'layer_key': layer_key,
            'bounds': bounds  # [min_lon, min_lat, max_lon, max_lat]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/check-overlaps', methods=['POST'])
def check_overlaps():
    """Vérifier les chevauchements entre une parcelle et les couches géographiques"""
    try:
        data = request.get_json()
        if not data or 'geojson' not in data:
            return jsonify({
                'success': False,
                'error': 'Données GeoJSON manquantes'
            }), 400
        
        geojson_data = data['geojson']
        
        # Trouver les parcelles dans le GeoJSON
        parcel_features = []
        if 'features' in geojson_data:
            parcel_features = [f for f in geojson_data['features'] 
                             if f.get('properties', {}).get('type') == 'parcel_boundary']
        
        if not parcel_features:
            return jsonify({
                'success': True,
                'overlaps': [],
                'message': 'Aucune parcelle trouvée pour vérifier les chevauchements'
            })
        
        all_overlaps = []
        
        # Vérifier chaque parcelle
        for i, parcel in enumerate(parcel_features):
            overlaps = layer_manager.check_overlaps(parcel)
            if overlaps:
                parcel_name = parcel.get('properties', {}).get('name', f'Parcelle {i+1}')
                all_overlaps.append({
                    'parcel_name': parcel_name,
                    'parcel_series': parcel.get('properties', {}).get('series', ''),
                    'overlaps': overlaps
                })
        
        return jsonify({
            'success': True,
            'overlaps': all_overlaps,
            'total_parcels_checked': len(parcel_features),
            'parcels_with_overlaps': len(all_overlaps)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("✅ Gestionnaire de couches initialisé avec {} couches".format(len(layer_manager.get_all_layers())))
    app.run(debug=True, host='0.0.0.0', port=5000)
