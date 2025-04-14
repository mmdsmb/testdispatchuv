from typing import Dict, Any
from app.db.item_repo import upsert_item_with_sqlalchemy, upsert_item_with_psycopg

class ItemService:
    @staticmethod
    def upsert_item(item_id: int, name: str, use_sqlalchemy: bool = True) -> Dict[str, Any]:
        """
        Upsert an item using either SQLAlchemy or psycopg.
        
        Args:
            item_id: The ID of the item
            name: The name of the item
            use_sqlalchemy: Whether to use SQLAlchemy (True) or psycopg (False)
            
        Returns:
            Dict containing the upserted item
        """
        if use_sqlalchemy:
            return upsert_item_with_sqlalchemy(item_id, name)
        return upsert_item_with_psycopg(item_id, name) 