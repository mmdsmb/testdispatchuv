from urllib.parse import quote
import httpx
import logging
from typing import Optional, Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)

async def test_geocoding_request(address: str, api_key: str) -> Optional[Tuple[str, dict]]:
    """
    Teste la requête de géocodage et loggue l'URL complète et la réponse de l'API.
    
    Args:
        address: Adresse à géocoder
        api_key: Clé API Google Maps
        
    Returns:
        Tuple (URL, réponse JSON) ou None si échec
    """
    encoded_address = quote(address)
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": encoded_address,
        "key": api_key,
        "region": "fr"
    }
    
    # Construction de l'URL complète pour vérification
    request_url = f"{base_url}?address={encoded_address}&key={api_key}&region=fr"
    logger.info(f"URL testée : {request_url}")  # Log critique pour vérification
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(base_url, params=params)
            data = response.json()
            
            logger.info(f"Réponse brute de l'API : {data}")  # Log complet de la réponse
            
            if data["status"] == "OK":
                logger.info("✅ Requête réussie - Clé et URL valides")
                location = data["results"][0]["geometry"]["location"]
                return (request_url, location)
            else:
                logger.error(f"❌ Erreur API : {data.get('error_message', data['status'])}")
                return (request_url, data)
                
    except Exception as e:
        logger.error(f"🚨 Erreur lors du test : {str(e)}")
        return None

# Exemple d'utilisation
async def run_test():
    test_address = "30 route de groslay 95200 sarcelles france"
    #test_api_key = "AIzaSyAQWAj6hmmEkt45CFPWu1fQCi7xx_xxxxx"  # Remplacez par votre vraie clé
    test_api_key = settings.GOOGLE_MAPS_API_KEY
    
    result = await test_geocoding_request(test_address, test_api_key)
    if result:
        url, response = result
        print(f"URL vérifiée : {url}")
        print(f"Coordonnées obtenues : {response}")
    else:
        print("Le test a échoué - vérifiez les logs")
        
if __name__ == "__main__":
    import asyncio
    asyncio.run(run_test())
