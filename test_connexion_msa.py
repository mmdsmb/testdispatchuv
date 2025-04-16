import asyncio
from app.db.postgres import PostgresDataSource

async def main():
    ds = PostgresDataSource()
    
    # Test de connexion
    health_status = await ds.health_check()
    print(f"Connection Health: {health_status}")
    
    # Nettoyage initial
    await ds.execute_query("DELETE FROM test_items WHERE name = 'item1'")
    
    try:
        # Création table si elle n'existe pas
        await ds.execute_query("""
            CREATE TABLE IF NOT EXISTS test_items (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                value INTEGER
            )
        """)
        
        # Premier insert avec vérification
        insert_result = await ds.execute_query("""
            INSERT INTO test_items (name, value)
            VALUES ('item1', 10)
            ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value
            RETURNING id, name, value
        """)
        
        print(f"Résultat premier insert: {insert_result}")

        
        # Vérification immédiate
        check_result = await ds.execute_query("SELECT * FROM test_items WHERE name = 'item1'")
        print(f"Vérification après insert: {check_result}")
        
        if not check_result:
            raise ValueError("L'insertion a échoué - aucun résultat trouvé")
        
        # Update via upsert
        update_result = await ds.execute_query("""
            INSERT INTO test_items (name, value)
            VALUES ('item1', 20)
            ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value
            RETURNING id, name, value
        """)
        print(f"Résultat update: {update_result}")

        
                # Update via upsert
        update_result = await ds.execute_query("""
            INSERT INTO test_items (name, value)
            VALUES ('item2', 056)
            ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value
            RETURNING id, name, value
        """)
        print(f"Résultat update: {update_result}")

        
        # Vérification finale
        final_check = await ds.execute_query("SELECT * FROM test_items WHERE name = 'item1'")
        print(f"Vérification finale: {final_check}")
        
        if not final_check or final_check[0][2] != 20:
            raise ValueError("La valeur n'a pas été correctement mise à jour")
            
        print("✅ Tous les tests d'upsert ont réussi")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        # Affichage du contenu complet de la table pour débogage
        all_items = await ds.execute_query("SELECT * FROM test_items")
        print(f"Contenu complet de la table: {all_items}")
    
    # Forcez un commit explicite après chaque opération
    await ds.execute_query("COMMIT")
    
    await ds.disconnect()

if __name__ == "__main__":
    asyncio.run(main())