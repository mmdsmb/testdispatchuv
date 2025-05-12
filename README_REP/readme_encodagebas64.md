# Script pour encoder les credentials (à exécuter une seule fois)
def encode_credentials_to_base64():
    # Lire le fichier JSON des credentials
    with open('credentials.json', 'r') as f:
        credentials_json = f.read()
    
    # Encoder en base64
    encoded = base64.b64encode(credentials_json.encode('utf-8')).decode('utf-8')
    
    print("Voici la valeur à copier dans fly.io secrets:")
    print(encoded)

# Exécuter cette fonction pour obtenir la valeur encodée
encode_credentials_to_base64()
