1. Initialize Git repository:
```bash
git init
```

2. Add files and commit:
```bash
git add .
git commit -m "Initial commit"
```

3. Add remote and push:
```bash
git config --global user.name "mmdsmb"
git config --global user.email "mmdsmb@gmail.com"
git remote set-url origin git@github.com:mmdsmb/testdispatchuv.git #  pour SSH et gérénétion de clé
git remote set-url origin https://github.com/mmdsmb/testdispatchuv.git # pour repo public
git push -u origin main
```

Différence entre `git pull` et `git fetch`, et quand utiliser chacun :

---

### **1. `git fetch`**
- **Ce que ça fait** :  
  Télécharge les derniers changements depuis le dépôt distant **sans modifier** vos fichiers locaux.  
  - Met à jour les références distantes (comme `origin/main`)  
  - Ne touche pas à votre branche locale  

- **Quand l'utiliser** :  
  - Vérifier les changements distants avant de les intégrer  
  - Inspecter l'historique avant un merge/rebase  
  - Commandes associées :  
    ```bash
    git fetch origin          # Récupère tout depuis le remote
    git fetch origin main     # Récupère uniquement la branche main
    git log origin/main..main # Voir les différences
    ```

---

### **2. `git pull`**
- **Ce que ça fait** :  
  `git fetch` + `git merge` (ou `git rebase`) en une seule commande.  
  - Télécharge les changements **et** les intègre à votre branche locale  

- **Quand l'utiliser** :  
  - Mettre à jour votre branche locale directement  
  - Commandes équivalentes :  
    ```bash
    git pull origin main      # = git fetch + git merge origin/main
    git pull --rebase origin main  # = git fetch + git rebase origin/main
    ```

---

### **Quelle commande choisir ?**
| Cas d'usage                      | `git fetch` | `git pull` |
|-----------------------------------|-------------|------------|
| Vérifier les changements distants | ✅          | ❌         |
| Mettre à jour sa branche locale   | ❌          | ✅         |
| Travailler sur une branche partagée | ✅ (d'abord) | ❌ (risque de conflits) |
| Intégrer des changements complexes | ✅ (préféré) | ❌         |

---

### **Bonnes Pratiques**
1. **Avant de commencer à travailler** :  
   ```bash
   git fetch origin
   git merge origin/main  # Ou git rebase
   ```
2. **Pour une mise à jour rapide** (si votre branche est simple) :  
   ```bash
   git pull --rebase origin main
   ```
3. **Si vous avez des modifications locales non commitées** :  
   Préférez `git fetch` puis `git stash`/`git rebase` pour éviter les conflits.

---

### **Exemple de Workflow Sécurisé**
```bash
# 1. Récupérer les changements distants
git fetch origin

# 2. Voir les différences
git diff main origin/main

# 3. Intégrer (merge ou rebase)
git merge origin/main
# OU
git rebase origin/main
```

> 💡 **Astuce** : Configurez Git pour utiliser `rebase` par défaut :  
> ```bash
> git config --global pull.rebase true
> ```

comment revenir au dernier commit distant. Il y a plusieurs approches possibles selon votre situation :
Si vous voulez simplement revenir au dernier commit distant sans perdre vos modifications locales :

```bash
# 1. Récupérer les changements distants
git fetch origin

```

perdre toutes vos modifications locales et revenir à l'état du dernier commit, vous pouvez utiliser la commande suivante
```bash
# 1. Récupérer les changements distants
git reset --hard HEAD

```

### **Solution Recommandée (sauvegarder vos modifications)**
1. **Stash (mise de côté temporaire)** :
   ```bash
   git stash save "Modifications locales avant pull"
   ```

2. **Effectuer le pull** :
   ```bash
   git pull origin main
   ```

3. **Récupérer vos modifications** :
   ```bash
   git stash pop  # Applique les modifications et supprime le stash
   ```

### **Si vous voulez annuler définitivement les modifications locales** (⚠️ irréversible) :
```bash
# 1. Annuler les modifications non commitées
git reset --hard HEAD

# 2. Annuler les fichiers stagés (si besoin)
git clean -fd

# 3. Pull
git pull origin main
```

### **Explications** :
- **`git stash`** :  
  Sauvegarde vos modifications dans une pile temporaire, vous permettant de les réappliquer après le pull.

- **`git reset --hard HEAD`** :  
  Réinitialise votre répertoire de travail à l'état du dernier commit (supprime toutes les modifications non commitées).

- **Pourquoi cette erreur ?**  
  Git refuse de fusionner (`pull` = `fetch` + `merge`) tant que vous avez des modifications non commitées qui pourraient être écrasées.

### **Workflow Complet (avec stash)** :
```bash
# 1. Vérifier l'état actuel
git status

# 2. Stash les modifications
git stash

# 3. Pull
git pull origin main

# 4. Récupérer le stash
git stash pop

# 5. Résoudre les conflits si nécessaire (ouvrir le fichier concerné)
```

### **Si vous avez des conflits après `stash pop`** :
1. Ouvrez le fichier conflictuel (comme `app/_main.ipynb`)  
2. Cherchez les marqueurs `<<<<<<<`, `=======`, `>>>>>>>`  
3. Corrigez manuellement, puis :  
   ```bash
   git add app/_main.ipynb
   git stash drop  # Supprime le stash appliqué
   ```

**Note** : Si vous utilisez Jupyter Notebook (`.ipynb`), les conflits peuvent être complexes à résoudre manuellement. Dans ce cas, envisagez de :
- Conserver une copie de sauvegarde du fichier avant toute opération  
- Utiliser `nbdiff` ou `jupyter-lab` pour les merges visuels


Si vous avez des modifications locales non sauvegardées dans le fichier `app/_main.ipynb`, vous pouvez suivre ces étapes :

1. Annulez les modifications locales :
   ```bash
   git checkout -- app/_main.ipynb
   ```

2. Récupérez les changements distants et intégrez-les :
   ```bash
   git pull
   ```

