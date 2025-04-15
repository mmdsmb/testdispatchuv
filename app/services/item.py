from typing import Dict, Any
from app.db.item_repo import upsert_item_with_sqlalchemy, upsert_item_with_psycopg
from datetime import datetime

class ItemService:
    @staticmethod
    def upsert_item(item_id: int, name: str, use_sqlalchemy: bool = True) -> Dict[str, Any]:
        """
        Upsert an item using either SQLAlchemy or psycopg.
        En cas d'erreur avec la première méthode, tente avec la seconde.
        
        Args:
            item_id: The ID of the item
            name: The name of the item
            use_sqlalchemy: Whether to use SQLAlchemy (True) or psycopg (False)
            
        Returns:
            Dict containing the upserted item
        """
        # Structure par défaut qui sera retournée en cas d'échec total
        default_result = {
            "id": item_id,
            "name": name,
            "updated_at": datetime.utcnow(),
            "status": "simulated",
            "message": "Opération simulée en raison de problèmes de connexion à la base de données"
        }
        
        # Journalisation pour le débogage
        print(f"Tentative d'upsert pour item_id={item_id}, name={name}")
        
        errors = []
        
        # Première tentative
        try:
            if use_sqlalchemy:
                print("Tentative avec SQLAlchemy...")
                result = upsert_item_with_sqlalchemy(item_id, name)
                if result.get("error"):
                    errors.append(f"SQLAlchemy error: {result.get('error')}")
                    print(f"Erreur SQLAlchemy: {result.get('error')}")
                    print("Fallback à psycopg...")
                    result = upsert_item_with_psycopg(item_id, name)
                    if result.get("error"):
                        errors.append(f"Psycopg error: {result.get('error')}")
                        print(f"Erreur Psycopg: {result.get('error')}")
                        # Les deux méthodes ont échoué
                        default_result["errors"] = errors
                        return default_result
                return result
            else:
                print("Tentative avec Psycopg...")
                result = upsert_item_with_psycopg(item_id, name)
                if result.get("error"):
                    errors.append(f"Psycopg error: {result.get('error')}")
                    print(f"Erreur Psycopg: {result.get('error')}")
                    print("Fallback à SQLAlchemy...")
                    result = upsert_item_with_sqlalchemy(item_id, name)
                    if result.get("error"):
                        errors.append(f"SQLAlchemy error: {result.get('error')}")
                        print(f"Erreur SQLAlchemy: {result.get('error')}")
                        # Les deux méthodes ont échoué
                        default_result["errors"] = errors
                        return default_result
                return result
        except Exception as e:
            errors.append(f"Exception initiale: {str(e)}")
            print(f"Exception lors de la tentative principale: {e}")
            try:
                if use_sqlalchemy:
                    print("Fallback à psycopg après exception SQLAlchemy...")
                    result = upsert_item_with_psycopg(item_id, name)
                    if result.get("error"):
                        errors.append(f"Psycopg error: {result.get('error')}")
                        print(f"Erreur Psycopg: {result.get('error')}")
                        default_result["errors"] = errors
                        return default_result
                    return result
                else:
                    print("Fallback à SQLAlchemy après exception psycopg...")
                    result = upsert_item_with_sqlalchemy(item_id, name)
                    if result.get("error"):
                        errors.append(f"SQLAlchemy error: {result.get('error')}")
                        print(f"Erreur SQLAlchemy: {result.get('error')}")
                        default_result["errors"] = errors
                        return default_result
                    return result
            except Exception as fallback_e:
                errors.append(f"Exception fallback: {str(fallback_e)}")
                print(f"Exception lors de la tentative de fallback: {fallback_e}")
                default_result["errors"] = errors
                return default_result 