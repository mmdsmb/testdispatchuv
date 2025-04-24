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
