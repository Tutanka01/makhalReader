# Déploiement de Baṣīra Frontend sur Cloudflare Pages via GitHub Actions

Cette documentation explique comment mettre en place le pipeline CI/CD automatisé pour déployer le frontend statique haute performance de **Baṣīra** sur Cloudflare Pages à chaque *push* sur la branche `main`.

---

## 1. Architecture du Déploiement

Dans une configuration locale ou VPS standard, Docker/Nginx redirige les appels `/api` vers le conteneur Python. Sur Cloudflare Pages, l'application est hébergée sur le réseau CDN mondial de Cloudflare.

Pour que votre frontend statique puisse communiquer avec votre backend hébergé sur votre serveur (ex: VPS Hetzner, Render, Fly.io) sans aucun problème de **CORS** ni exposer l'URL directe de votre API, nous utilisons une **Cloudflare Pages Function** (définie dans `frontend/functions/api/[[path]].ts`).

### Fonctionnement du Reverse Proxy Edge
1. Votre application Vite fait des appels relatifs habituels : `fetch('/api/articles')`.
2. Cloudflare Pages intercepte la requête à l'Edge grâce à la fonction `[[path]].ts`.
3. Elle redirige la requête vers `https://api.basira.votredomaine.com/api/articles`.

---

## 2. Prérequis sur Cloudflare

1. Connectez-vous à votre compte **Cloudflare** et naviguez vers **Workers & Pages**.
2. Créez un projet **Pages** (vous pouvez le nommer `basira-reader`).
3. Dans les **Paramètres (Settings) > Variables d'environnement (Environment variables)** du projet, ajoutez :
   * Nom de la variable : `API_BASE_URL`
   * Valeur : `https://api.basira.votredomaine.com` *(l'URL HTTPS publique de votre backend API)*

---

## 3. Configuration de GitHub Actions (CI/CD)

Le workflow automatisé est déjà créé et configuré dans `.github/workflows/deploy-pages.yml`.

Pour l'activer, rendez-vous sur la page de votre dépôt sur **GitHub > Settings > Secrets and variables > Actions**, et ajoutez les deux secrets suivants :

| Secret GitHub | Description / Obtention |
|---------------|-------------------------|
| `CLOUDFLARE_ACCOUNT_ID` | Votre Account ID Cloudflare (trouvable en bas à droite de votre tableau de bord Cloudflare). |
| `CLOUDFLARE_API_TOKEN` | Un jeton d'API Cloudflare. Créez-le sur votre profil Cloudflare > API Tokens avec la permission **Cloudflare Pages > Edit**. |

---

## 4. Déploiement

À chaque fois que vous ferez un `git push` sur la branche `main` (ou lors d'une modification dans le dossier `frontend/`), l'action GitHub va :
1. Cloner le code et installer Node.js 20.
2. Lancer `npm ci` et `npm run build`.
3. Déployer instantanément le contenu du dossier compilé (`frontend/dist`) ainsi que la fonction proxy sur votre domaine `.pages.dev` ou votre domaine personnalisé configuré dans Cloudflare.
