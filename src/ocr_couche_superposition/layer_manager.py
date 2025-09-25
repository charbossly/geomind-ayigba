import json
import os
from typing import Dict, List, Any, Optional
import geojson

# Import optionnel de geopandas pour des performances améliorées
try:
    import geopandas as gpd
    from shapely.geometry import shape
    GEOPANDAS_AVAILABLE = True
    print("🚀 GeoPandas disponible - Utilisation d'algorithmes géométriques optimisés")
except ImportError:
    GEOPANDAS_AVAILABLE = False
    print("📐 GeoPandas non disponible - Utilisation d'algorithmes géométriques basiques")

class LayerManager:
    """Gestionnaire des couches géographiques GeoJSON"""
    
    def __init__(self, layers_directory: str = "couche"):
        self.layers_directory = layers_directory
        self.layers = {}
        self.layer_metadata = {}
        self.load_all_layers()
    
    def load_all_layers(self):
        """Charger toutes les couches GeoJSON du dossier"""
        print("🗺️ Chargement des couches géographiques...")
        print(f"📂 Dossier des couches: {self.layers_directory}")
        
        if not os.path.exists(self.layers_directory):
            print(f"❌ Dossier {self.layers_directory} non trouvé")
            return
        
        # Définition des couches avec leurs métadonnées
        # Note: 'parcelles' sera chargée à la demande selon la localisation
        layer_definitions = {
            'aif': {
                'name': 'AIF (Aires d\'Intérêt Foncier)',
                'description': 'Zones d\'intérêt foncier identifiées',
                'color': '#FF6B6B',
                'visible': False,
                'type': 'polygon'
            },
            'air_proteges': {
                'name': 'Aires Protégées',
                'description': 'Zones de protection environnementale',
                'color': '#4ECDC4',
                'visible': False,
                'type': 'polygon'
            },
            'dpl': {
                'name': 'DPL (Domaine Public Local)',
                'description': 'Domaine public local',
                'color': '#45B7D1',
                'visible': False,
                'type': 'polygon'
            },
            'dpm': {
                'name': 'DPM (Domaine Public Maritime)',
                'description': 'Domaine public maritime',
                'color': '#96CEB4',
                'visible': False,
                'type': 'polygon'
            },
            'enregistrement individuel': {
                'name': 'Enregistrements Individuels',
                'description': 'Enregistrements fonciers individuels',
                'color': '#FFEAA7',
                'visible': False,
                'type': 'point'
            },
            'litige': {
                'name': 'Litiges Fonciers',
                'description': 'Zones en litige foncier',
                'color': '#FD79A8',
                'visible': False,
                'type': 'polygon'
            },
            'parcelles': {
                'name': 'Parcelles',
                'description': 'Parcelles cadastrales',
                'color': '#A29BFE',
                'visible': False,
                'type': 'polygon'
            },
            'restriction': {
                'name': 'Restrictions',
                'description': 'Zones avec restrictions d\'usage',
                'color': '#FD7272',
                'visible': False,
                'type': 'polygon'
            },
            'tf_demembres': {
                'name': 'TF Démembrés',
                'description': 'Titres fonciers démembrés',
                'color': '#74B9FF',
                'visible': False,
                'type': 'polygon'
            },
            'tf_en_cours': {
                'name': 'TF En Cours',
                'description': 'Titres fonciers en cours de traitement',
                'color': '#FDCB6E',
                'visible': False,
                'type': 'polygon'
            },
            'tf_etat': {
                'name': 'TF État',
                'description': 'Titres fonciers de l\'État',
                'color': '#6C5CE7',
                'visible': False,
                'type': 'polygon'
            },
            'titre_reconstitue': {
                'name': 'Titres Reconstitués',
                'description': 'Titres fonciers reconstitués',
                'color': '#00B894',
                'visible': False,
                'type': 'polygon'
            },
            'zone_inondable': {
                'name': 'Zones Inondables',
                'description': 'Zones à risque d\'inondation',
                'color': '#0984E3',
                'visible': False,
                'type': 'polygon'
            }
        }
        
        loaded_count = 0
        for layer_key, metadata in layer_definitions.items():
            # Exclure 'parcelles' du chargement automatique (trop volumineux)
            if layer_key == 'parcelles':
                # Juste enregistrer les métadonnées, pas les données
                self.layer_metadata[layer_key] = metadata
                print(f"📋 Couche '{layer_key}' enregistrée (chargement à la demande)")
                continue
                
            geojson_file = os.path.join(self.layers_directory, f"{layer_key}.geojson")
            
            if os.path.exists(geojson_file):
                try:
                    layer_data = self.load_layer_file(geojson_file, layer_key)
                    if layer_data:
                        self.layers[layer_key] = layer_data
                        self.layer_metadata[layer_key] = metadata
                        loaded_count += 1
                        
                        feature_count = len(layer_data.get('features', []))
                        print(f"✅ Couche '{layer_key}' chargée: {feature_count} éléments")
                    
                except Exception as e:
                    print(f"❌ Erreur lors du chargement de {layer_key}: {e}")
        
        print(f"📊 Total: {loaded_count} couches chargées (+ parcelles à la demande)")
    
    def load_layer_file(self, file_path: str, layer_key: str) -> Optional[Dict]:
        """Charger un fichier GeoJSON complet"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Afficher le progrès pour les gros fichiers
            if 'features' in data:
                feature_count = len(data['features'])
                if feature_count > 100:
                    for i in range(0, feature_count, 100):
                        print(f"   📍 {layer_key}: {min(i+100, feature_count)} éléments traités...")
            
            return data
            
        except Exception as e:
            print(f"❌ Erreur lors du chargement de {file_path}: {e}")
            return None
    
    def get_layer(self, layer_key: str) -> Optional[Dict]:
        """Récupérer une couche spécifique"""
        return self.layers.get(layer_key)
    
    def get_all_layers(self) -> Dict[str, Dict]:
        """Récupérer toutes les couches"""
        return self.layers
    
    def get_layer_metadata(self, layer_key: str) -> Optional[Dict]:
        """Récupérer les métadonnées d'une couche"""
        return self.layer_metadata.get(layer_key)
    
    def get_all_metadata(self) -> Dict[str, Dict]:
        """Récupérer toutes les métadonnées des couches"""
        return self.layer_metadata
    
    def get_layers_summary(self) -> List[Dict]:
        """Récupérer un résumé de toutes les couches pour l'interface"""
        summary = []
        for layer_key, metadata in self.layer_metadata.items():
            layer_data = self.layers.get(layer_key, {})
            feature_count = len(layer_data.get('features', []))
            
            summary.append({
                'key': layer_key,
                'name': metadata['name'],
                'description': metadata['description'],
                'color': metadata['color'],
                'visible': metadata['visible'],
                'type': metadata['type'],
                'feature_count': feature_count
            })
        
        return summary
    
    def get_layer_bounds(self, layer_key: str) -> Optional[List[float]]:
        """Calculer les bounds d'une couche"""
        layer = self.get_layer(layer_key)
        if not layer or 'features' not in layer:
            return None
        
        min_lon, min_lat = float('inf'), float('inf')
        max_lon, max_lat = float('-inf'), float('-inf')
        
        for feature in layer['features']:
            geometry = feature.get('geometry', {})
            if geometry.get('type') == 'Point':
                lon, lat = geometry['coordinates']
                min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
            elif geometry.get('type') in ['Polygon', 'MultiPolygon']:
                coords = geometry['coordinates']
                if geometry['type'] == 'Polygon':
                    coords = [coords]
                
                for polygon in coords:
                    for ring in polygon:
                        for lon, lat in ring:
                            min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                            min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
        
        if min_lon != float('inf'):
            return [min_lon, min_lat, max_lon, max_lat]
        
        return None
    
    def check_overlaps(self, geojson_feature) -> List[Dict]:
        """Vérifier les chevauchements entre une feature et toutes les couches"""
        overlaps = []
        
        if not geojson_feature or geojson_feature.get('geometry', {}).get('type') != 'Polygon':
            return overlaps
        
        # Extraire les coordonnées de la parcelle pour déterminer le centre
        parcel_coords = geojson_feature['geometry']['coordinates'][0]
        
        # Calculer le centre de la parcelle pour le chargement des parcelles locales
        center_lat = sum(coord[1] for coord in parcel_coords) / len(parcel_coords)
        center_lon = sum(coord[0] for coord in parcel_coords) / len(parcel_coords)
        
        # Charger les parcelles dans un rayon de 1km autour de la parcelle analysée
        parcelles_data = self.load_parcelles_by_location(center_lat, center_lon, 1000)
        if parcelles_data:
            # Ajouter temporairement les parcelles aux couches pour la vérification
            self.layers['parcelles'] = parcelles_data
            print(f"📍 {len(parcelles_data['features'])} parcelles chargées pour l'analyse")
        
        # Vérifier chaque couche (y compris les parcelles maintenant chargées)
        for layer_key, layer_data in self.layers.items():
            if not layer_data or 'features' not in layer_data:
                continue
            
            layer_metadata = self.layer_metadata.get(layer_key, {})
            overlapping_features = []
            
            # Vérifier chaque feature de la couche
            for feature in layer_data['features']:
                if self._features_overlap(geojson_feature, feature):
                    overlapping_features.append({
                        'properties': feature.get('properties', {}),
                        'geometry_type': feature.get('geometry', {}).get('type', 'Unknown')
                    })
            
            if overlapping_features:
                overlaps.append({
                    'layer_key': layer_key,
                    'layer_name': layer_metadata.get('name', layer_key),
                    'layer_description': layer_metadata.get('description', ''),
                    'layer_color': layer_metadata.get('color', '#000000'),
                    'overlapping_count': len(overlapping_features),
                    'features': overlapping_features[:5]  # Limiter à 5 features pour l'affichage
                })
        
        # Nettoyer les parcelles de la mémoire après utilisation
        if 'parcelles' in self.layers and parcelles_data:
            del self.layers['parcelles']
            print("🧹 Parcelles supprimées de la mémoire après analyse")
        
        return overlaps
    
    def _features_overlap(self, feature1, feature2) -> bool:
        """Vérifier si deux features se chevauchent avec algorithme géométrique précis"""
        try:
            geom1 = feature1.get('geometry', {})
            geom2 = feature2.get('geometry', {})
            
            if not geom1 or not geom2:
                return False
            
            # Utiliser geopandas/shapely si disponible pour de meilleures performances
            if GEOPANDAS_AVAILABLE:
                return self._geometries_intersect_optimized(geom1, geom2)
            else:
                # Utiliser l'algorithme géométrique basique
                return self._geometries_intersect(geom1, geom2)
            
        except Exception as e:
            print(f"Erreur lors de la vérification de chevauchement: {e}")
            return False
    
    def _geometries_intersect_optimized(self, geom1, geom2) -> bool:
        """Vérification d'intersection optimisée avec Shapely/GeoPandas"""
        try:
            # Convertir les géométries GeoJSON en objets Shapely
            shape1 = shape(geom1)
            shape2 = shape(geom2)
            
            # Utiliser l'algorithme optimisé de Shapely
            return shape1.intersects(shape2)
            
        except Exception as e:
            print(f"Erreur avec Shapely, fallback sur algorithme basique: {e}")
            # Fallback sur l'algorithme basique
            return self._geometries_intersect(geom1, geom2)
    
    def _geometries_intersect(self, geom1, geom2) -> bool:
        """Vérifier si deux géométries s'intersectent (algorithme précis)"""
        type1 = geom1.get('type')
        type2 = geom2.get('type')
        coords1 = geom1.get('coordinates', [])
        coords2 = geom2.get('coordinates', [])
        
        if not coords1 or not coords2:
            return False
        
        # Point dans Polygon
        if type1 == "Point" and type2 == "Polygon":
            return self._point_in_polygon(coords1, coords2[0])
        elif type1 == "Polygon" and type2 == "Point":
            return self._point_in_polygon(coords2, coords1[0])
        
        # Polygon avec Polygon
        elif type1 == "Polygon" and type2 == "Polygon":
            # Vérifier si au moins un point du premier polygone est dans le second
            for coord in coords1[0]:
                if self._point_in_polygon(coord, coords2[0]):
                    return True
            # Vérifier l'inverse
            for coord in coords2[0]:
                if self._point_in_polygon(coord, coords1[0]):
                    return True
            return False
        
        # Point avec Point
        elif type1 == "Point" and type2 == "Point":
            return (coords1[0] == coords2[0] and coords1[1] == coords2[1])
        
        # MultiPolygon
        elif type1 == "MultiPolygon":
            for polygon in coords1:
                temp_geom = {"type": "Polygon", "coordinates": polygon}
                if self._geometries_intersect(temp_geom, geom2):
                    return True
            return False
        elif type2 == "MultiPolygon":
            for polygon in coords2:
                temp_geom = {"type": "Polygon", "coordinates": polygon}
                if self._geometries_intersect(geom1, temp_geom):
                    return True
            return False
        
        # LineString (approximation avec bounds pour performance)
        elif type1 == "LineString" or type2 == "LineString":
            # Fallback sur bounds pour les lignes (plus complexe à implémenter précisément)
            bounds1 = self._get_feature_bounds(geom1)
            bounds2 = self._get_feature_bounds(geom2)
            if bounds1 and bounds2:
                return self._bounds_overlap(bounds1, bounds2)
        
        return False
    
    def _point_in_polygon(self, point, polygon) -> bool:
        """Algorithme Ray-casting pour déterminer si un point est dans un polygone"""
        x, y = point[0], point[1]
        inside = False
        
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = polygon[i][0], polygon[i][1]
            xj, yj = polygon[j][0], polygon[j][1]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        
        return inside
    
    def load_parcelles_by_location(self, lat: float, lon: float, radius_meters: int = 1000) -> Optional[Dict]:
        """
        Charger les parcelles dans un rayon donné autour d'un point
        Utilise la même méthode que le projet 'chevauchement'
        """
        try:
            import math
            from shapely.geometry import Point, shape
            
            parcelles_path = os.path.join(self.layers_directory, 'parcelles.geojson')
            
            if not os.path.exists(parcelles_path):
                print(f"❌ Fichier parcelles.geojson non trouvé dans {self.layers_directory}")
                return None
            
            print(f"🎯 Chargement parcelles autour de ({lat}, {lon}) dans un rayon de {radius_meters}m")
            
            # Convertir le rayon en degrés approximatifs (pour WGS84)
            # 1 degré ≈ 111,320 mètres à l'équateur
            radius_degrees = radius_meters / 111320.0
            
            # Créer une bounding box pour pré-filtrer
            min_lon = lon - radius_degrees
            max_lon = lon + radius_degrees
            min_lat = lat - radius_degrees
            max_lat = lat + radius_degrees
            
            print(f"🔍 Bounding box: ({min_lat:.6f}, {min_lon:.6f}) à ({max_lat:.6f}, {max_lon:.6f})")
            
            # Filtrer les parcelles par streaming
            filtered_features = []
            feature_count = 0
            processed_count = 0
            
            # Lire le fichier ligne par ligne pour éviter de charger tout en mémoire
            with open(parcelles_path, 'r', encoding='utf-8') as f:
                current_feature = ""
                brace_count = 0
                in_features = False
                
                for line in f:
                    if not in_features:
                        if '"features": [' in line:
                            in_features = True
                        continue
                    
                    current_feature += line
                    brace_count += line.count('{') - line.count('}')
                    
                    if brace_count == 0 and current_feature.strip():
                        try:
                            # Nettoyer et parser la feature
                            clean_feature = current_feature.strip().rstrip(',')
                            feature_obj = json.loads(clean_feature)
                            processed_count += 1
                            
                            # Vérification rapide avec bounding box
                            if feature_obj.get('geometry'):
                                geom = feature_obj['geometry']
                                
                                # Extraire les coordonnées selon le type de géométrie
                                coords = None
                                if geom['type'] == 'Polygon':
                                    coords = geom['coordinates'][0]  # Premier ring du polygone
                                elif geom['type'] == 'Point':
                                    coords = [geom['coordinates']]
                                elif geom['type'] == 'MultiPolygon':
                                    coords = geom['coordinates'][0][0]  # Premier ring du premier polygone
                                
                                if coords:
                                    # Vérifier si au moins un point est dans la bounding box
                                    in_bbox = any(
                                        min_lon <= coord[0] <= max_lon and min_lat <= coord[1] <= max_lat
                                        for coord in coords
                                    )
                                    
                                    if in_bbox:
                                        # Vérification plus précise avec la distance
                                        geom_shape = shape(geom)
                                        
                                        # Calculer la distance au centroïde de la parcelle
                                        centroid = geom_shape.centroid
                                        distance = self._calculate_distance(lat, lon, centroid.y, centroid.x)
                                        
                                        if distance <= radius_meters:
                                            filtered_features.append(feature_obj)
                                            feature_count += 1
                            
                            current_feature = ""
                            
                            # Limiter le nombre de résultats pour éviter la surcharge
                            if feature_count >= 5000:  # Limite de sécurité
                                print(f"⚠️ Limite de 5000 parcelles atteinte")
                                break
                                
                        except json.JSONDecodeError:
                            current_feature = ""
                            brace_count = 0
                        except Exception as e:
                            print(f"Erreur lors du traitement d'une parcelle: {e}")
                            current_feature = ""
                            brace_count = 0
                            
                        # Afficher le progrès
                        if processed_count % 10000 == 0:
                            print(f"   📍 {processed_count} parcelles traitées, {feature_count} sélectionnées...")
            
            print(f"✅ Filtrage terminé: {feature_count} parcelles trouvées sur {processed_count} traitées")
            
            # Construire le GeoJSON de résultat
            result = {
                'type': 'FeatureCollection',
                'features': filtered_features,
                'metadata': {
                    'center_lat': lat,
                    'center_lon': lon,
                    'radius_meters': radius_meters,
                    'feature_count': feature_count,
                    'processed_count': processed_count
                }
            }
            
            return result
            
        except Exception as e:
            print(f"❌ Erreur lors du chargement des parcelles par localisation: {e}")
            return None
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calcule la distance en mètres entre deux points GPS
        en utilisant la formule de Haversine
        """
        import math
        
        # Convertir en radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Formule de Haversine
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Rayon de la Terre en mètres
        r = 6371000
        
        return c * r
    
    def _get_feature_bounds(self, geometry) -> Optional[List[float]]:
        """Calculer les bounds d'une geometry"""
        try:
            geom_type = geometry.get('type')
            coords = geometry.get('coordinates', [])
            
            if not coords:
                return None
            
            min_lon, min_lat = float('inf'), float('inf')
            max_lon, max_lat = float('-inf'), float('-inf')
            
            if geom_type == 'Point':
                lon, lat = coords
                return [lon, lat, lon, lat]
            
            elif geom_type == 'Polygon':
                for ring in coords:
                    for coord in ring:
                        if len(coord) >= 2:
                            lon, lat = coord[0], coord[1]
                            min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                            min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
            
            elif geom_type == 'MultiPolygon':
                for polygon in coords:
                    for ring in polygon:
                        for coord in ring:
                            if len(coord) >= 2:
                                lon, lat = coord[0], coord[1]
                                min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                                min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
            
            elif geom_type == 'LineString':
                for coord in coords:
                    if len(coord) >= 2:
                        lon, lat = coord[0], coord[1]
                        min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                        min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
            
            if min_lon != float('inf'):
                return [min_lon, min_lat, max_lon, max_lat]
            
            return None
            
        except Exception as e:
            print(f"Erreur lors du calcul des bounds: {e}")
            return None
    
    def _bounds_overlap(self, bounds1, bounds2) -> bool:
        """Vérifier si deux bounds se chevauchent"""
        min_lon1, min_lat1, max_lon1, max_lat1 = bounds1
        min_lon2, min_lat2, max_lon2, max_lat2 = bounds2
        
        # Pas de chevauchement si séparés horizontalement ou verticalement
        if (max_lon1 < min_lon2 or max_lon2 < min_lon1 or 
            max_lat1 < min_lat2 or max_lat2 < min_lat1):
            return False
        
        return True

# Instance globale du gestionnaire de couches
layer_manager = LayerManager()
