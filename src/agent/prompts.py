from datetime import datetime

# Date actuelle au format lisible
def get_current_date():
    return datetime.now().strftime("%d %B %Y")


# Générateur de requêtes pour recherche foncière au Bénin
query_writer_instructions = """Ton objectif est de générer des requêtes de recherche web précises et variées sur le domaine foncier au Bénin. 
Ces requêtes sont destinées à un outil automatique avancé capable d’analyser les résultats récents, de suivre les liens et de synthétiser l’information.

Instructions :
- Formule les requêtes uniquement en français.
- Préfère une seule requête, sauf si plusieurs aspects sont nécessaires pour bien répondre à la question.
- Chaque requête doit être claire, simple et compréhensible par tout utilisateur.
- Ne pas dépasser {number_queries} requêtes.
- La requête doit garantir que l’information la plus récente est recueillie (date actuelle : {current_date}).
- Les recherches doivent rester centrées sur le domaine foncier au Bénin (procédures, lois, démarches, coûts, risques, arnaques, actualités, etc.).

Format de sortie :
- JSON avec deux clés obligatoires :
   - "rationale": une brève explication de pourquoi cette requête est pertinente
   - "query": une liste de requêtes de recherche

Contexte : {research_topic}
"""


# Instructions pour effectuer la recherche
web_searcher_instructions = """Effectue des recherches Google ciblées afin de rassembler les informations les plus récentes et crédibles 
sur le sujet suivant (lié au foncier au Bénin) : "{research_topic}"

Instructions :
- Les requêtes doivent être en français et adaptées au contexte béninois.
- Conduis plusieurs recherches variées pour avoir une information complète.
- Résume les points essentiels sous forme de texte clair, simple et compréhensible par tous.
- Pour chaque information, mentionne clairement la source avec un lien cliquable.
- Ne jamais inventer d’information : n’utilise que ce qui est trouvé dans les résultats.

Sujet de recherche :
{research_topic}
"""


# Instructions pour réfléchir sur les résumés
reflection_instructions = """Tu es un assistant expert qui analyse des résumés d’information concernant le foncier au Bénin : "{research_topic}"

Instructions :
- Identifie s’il manque des détails importants (procédures, coûts, risques, acteurs officiels, lois, délais, documents nécessaires, etc.).
- Si les résumés sont suffisants, indique-le.
- Sinon, propose une ou plusieurs requêtes de suivi (en français) pour combler les manques.

Format attendu (JSON) :
{{
    "is_sufficient": true/false,
    "knowledge_gap": "Informations manquantes ou insuffisantes",
    "follow_up_queries": ["Nouvelle requête de recherche en français"]
}}

Résumés :
{summaries}
"""


# Instructions pour générer la réponse finale
answer_instructions = """
Ta mission est de générer un résumé **extrêmement concis** (2 à 3 phrases maximum) basé sur les informations fournies.

Instructions :
- La réponse doit être en français.
- **Résume** l'information la plus importante en 2 ou 3 phrases.
- **N'ajoute aucune explication ou détail superflu.**
- Après le résumé, liste simplement les sources les plus pertinentes en utilisant les liens fournis dans les résumés.
- Agis comme un aperçu rapide, pas comme un rapport complet.

Contexte utilisateur :
- {research_topic}

Résumés de recherche :
{summaries}
"""