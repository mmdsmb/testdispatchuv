import os
import subprocess
import threading
import uuid
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import time
from supabase import create_client, Client
import pandas as pd


app = Flask(__name__)
CORS(app)  # Permettre les requêtes cross-origin depuis FlutterFlow

# Stockage des tâches en cours et terminées
tasks = {}

@app.route('/')
def hello():
    return "Hello World!"

# Récupérer les variables d'environnement
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Vérifier si les variables sont bien chargées
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Les variables d'environnement SUPABASE_URL et SUPABASE_KEY ne sont pas définies.")

# Initialisation de la connexion Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


from datetime import datetime

def save_task_to_supabase(task_id, status, start_time, elapsed_time, result_file, output, error,results=None):
    # Convertir le timestamp UNIX en format ISO 8601
    start_time_iso = datetime.utcfromtimestamp(start_time).isoformat()  # Convertit correctement
    
    response = supabase.table("tasks").upsert({
        "id": task_id,
        "status": status,
        "start_time": start_time_iso,  
        "elapsed_time_min": elapsed_time/60,
        "result_file": result_file,
        "output": output,
        "error": error,
        "results": results
    }).execute()


def run_dispatch_script(task_id, date_param=None):
    """Exécute le script dispatch.py en arrière-plan"""
    try:
        # Mise à jour du statut
        tasks[task_id]["status"] = "running"
        
        # Suppression du fichier s'il existe déjà
        output_file = "affectations_groupes_chauffeurs_final.csv"
        if os.path.exists(output_file):
            os.remove(output_file)

        # Commande pour exécuter le script dispatch.py
        cmd = ["python", "dispatch.py"]

        # Ajouter la date en paramètre si fournie
        if date_param:
            cmd.append(date_param)

        # Exécuter le script et capturer sa sortie
        start_time = time.time()
        process = subprocess.run(cmd, capture_output=True, text=True)
        elapsed_time = time.time() - start_time

        # Enregistrer dans Supabase
        if process.returncode == 0:
            if os.path.exists(output_file):
                
                task = tasks[task_id]
                results_file = task.get("result_file", "affectations_groupes_chauffeurs_final.csv")
                df = pd.read_csv(results_file)
                results = df.to_dict(orient='records')
                # Transformer en JSON string
                results_json = json.dumps(results, ensure_ascii=False)  # UTF-8 support
                
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["result_file"] = output_file
                tasks[task_id]["output"] = process.stdout
                tasks[task_id]["elapsed_time"] = elapsed_time/60
                tasks[task_id]["results"] = results_json
                save_task_to_supabase(task_id, "completed", tasks[task_id]["start_time"], elapsed_time, output_file, process.stdout, None,results_json)
            else:
                tasks[task_id]["status"] = "error"
                tasks[task_id]["error"] = "Le fichier de résultats n'a pas été généré"
                save_task_to_supabase(task_id, "error", tasks[task_id]["start_time"], elapsed_time, None, None, "Le fichier de résultats n'a pas été généré")
        else:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["error"] = process.stderr
            save_task_to_supabase(task_id, "error", tasks[task_id]["start_time"], elapsed_time, None, process.stdout, process.stderr)

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)
        save_task_to_supabase(task_id, "error", tasks[task_id]["start_time"], time.time() - tasks[task_id]["start_time"], None, None, str(e))


@app.route('/dispatch', methods=['POST'])
def start_dispatch():
    """Endpoint pour lancer l'exécution du script dispatch.py"""
    # Générer un ID unique pour cette tâche
    task_id = str(uuid.uuid4())

    # Récupérer les paramètres optionnels
    date_param = request.json.get('date') if request.json else None

    # Initialiser la tâche
    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "start_time": time.time(),
        "date_param": date_param
    }

    # Lancer l'exécution en arrière-plan
    thread = threading.Thread(target=run_dispatch_script, args=(task_id, date_param))
    thread.daemon = True
    thread.start()

    return jsonify({
        "task_id": task_id,
        "status": "pending",
        "message": "Tâche de planification lancée avec succès"
    })

@app.route('/status/<task_id>', methods=['GET'])
def check_status(task_id):
    """Endpoint pour vérifier le statut d'une tâche"""
    if task_id not in tasks:
        return jsonify({"error": "Tâche non trouvée"}), 404

    task = tasks[task_id]
    response = {
        "task_id": task_id,
        "status": task["status"],
        "elapsed_time": (time.time() - task["start_time"])/60
    }

    # Ajouter des infos supplémentaires selon le statut
    if task["status"] == "completed":
        response["result"] = "success"
        response["message"] = "Planification terminée avec succès"
        response["actual_processing_time"] = task.get("elapsed_time", 0)
    elif task["status"] == "error":
        response["result"] = "error"
        response["message"] = "Erreur lors de la planification"
        response["error_details"] = task.get("error", "Erreur inconnue")

    return jsonify(response)

@app.route('/results_supabase/<task_id>', methods=['GET'])
def get_results_supabase(task_id):
    """Endpoint pour récupérer les résultats d'une tâche terminée"""    
    response = supabase.table("tasks").select("*").eq("id", task_id).execute()
    
    if not response.data or len(response.data) == 0:
        #return jsonify({"error": "Tâche non trouvée dans supabase donc non fini"}), 404
        return check_status(task_id)
    
    task = response.data[0]  # Récupérer la première tâche
    
    response_data = {
        "task_id": task_id,
        "status": task.get("status"),
        "elapsed_time": task.get("elapsed_time_min")
    }
    
    if task.get("status") == "completed":
        response_data.update({
            "result": "success",
            "message": "Planification terminée avec succès",
            "actual_processing_time": task.get("elapsed_time_min"),
            "result_file": task.get("result_file")
        })
    elif task.get("status") == "error":
        response_data.update({
            "result": "error",
            "message": "Erreur lors de la planification",
            "error_details": task.get("error")
        })
    
    return jsonify(response_data)



@app.route('/results/<task_id>', methods=['GET'])
def get_results(task_id):
    """Endpoint pour récupérer les résultats d'une tâche terminée"""
    if task_id not in tasks:
        return jsonify({"error": "Tâche non trouvée"}), 404

    task = tasks[task_id]

    if task["status"] != "completed":
        return jsonify({
            "task_id": task_id,
            "status": task["status"],
            "elapsed_time": ((time.time() - task["start_time"])/60),
            "message": "Les résultats ne sont pas encore disponibles"
        })

    # Lire le fichier CSV de résultats
    try:
        import pandas as pd
        results_file = task.get("result_file", "affectations_groupes_chauffeurs_final.csv")
        df = pd.read_csv(results_file)
        results = df.to_dict(orient='records')

        return jsonify({
            "task_id": task_id,
            "status": "completed",
            "results": results,
            "elapsed_time": ((time.time() - task["start_time"])/60),
            "count": len(results)
        })
    except Exception as e:
        return jsonify({
            "task_id": task_id,
            "status": "error",
            "message": "Erreur lors de la lecture des résultats",
            "error": str(e)
        }), 500
        
if __name__ == '__main__':
    # Pour le développement local uniquement
    app.run(host='0.0.0.0', port=8080, debug=True)
