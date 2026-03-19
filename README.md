<div align="center">

# ◉ MakhalReader

**Un lecteur RSS qui pense à ta place.**

*Conçu pour les ingénieurs qui ont trop à lire et trop peu de temps.*

---

[![Made with FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React%2018-61DAFB?style=flat-square&logo=react)](https://react.dev)
[![Docker](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED?style=flat-square&logo=docker)](https://docs.docker.com/compose/)
[![PWA](https://img.shields.io/badge/PWA-Offline%20Ready-5A0FC8?style=flat-square&logo=pwa)](https://web.dev/progressive-web-apps/)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20WAL-003B57?style=flat-square&logo=sqlite)](https://sqlite.org)

</div>

---

## Le problème

Les agrégateurs RSS classiques affichent **tout** — du post de blog bateau à l'analyse de fond qui change ta façon de concevoir l'infra. Résultat : tu passes plus de temps à trier qu'à lire.

MakhalReader résout ça. Chaque article est **scoré par un LLM** avant même que tu ne l'ouvres.

---

## Ce que ça fait

```
RSS Feeds  →  Extraction  →  Score LLM (0-10)  →  Lecture
   32+           full-text      Gemini / Ollama      Reader
  sources        contenu        tags, résumé         épuré
```

Quand tu ouvres l'app, tu ne vois que ce qui vaut ton temps.

---

## Une seule commande pour démarrer

```bash
# 1. Copier et configurer les variables d'environnement
cp .env.example .env
# → Renseigne OPENROUTER_API_KEY (ou laisse vide pour Ollama local)

# 2. Lancer
docker compose up -d
```

L'app est disponible sur **http://localhost**. C'est tout.

> Aucune dépendance à installer. Aucune base de données à configurer. Aucune migration à lancer.

---

## Les fonctionnalités qui comptent

### Scoring IA personnalisé

Chaque article reçoit un **score de 0 à 10** basé sur ton profil technique réel.
Le scorer comprend la différence entre un post-mortem Kubernetes qui vaut la peine d'être lu
et un énième "10 tips pour devenir senior developer".

```
0–2  ·  Du bruit      →  Jamais affiché
3–5  ·  Correct       →  Disponible si tu cherches
6–7  ·  Bon           →  En tête de liste
8–10 ·  Exceptionnel  →  Digest du jour
```

Tags automatiques · Bullets de résumé · Justification du score — directement dans l'interface.

---

### Digest du jour

Un onglet **Digest** agrège les meilleurs articles des dernières 24h (ou 48h) classés par tier :

```
🔥 Excellent  ·  score ≥ 9
⭐ Top        ·  score ≥ 7
👍 Bon        ·  score ≥ 5
```

C'est ta revue de presse du matin, sans effort.

---

### Déduplication intelligente à 3 couches

Les mêmes articles apparaissent souvent dans plusieurs feeds (Hacker News, Lobsters, agrégateurs...).
MakhalReader ne les stocke qu'une seule fois :

1. **URL canonique** — normalisée (sans tracking params, `www.`, trailing slash)
2. **Empreinte de titre** — pour les articles syndiqués avec URL différente
3. **`<link rel="canonical">`** — la source fait foi

---

### Interface pensée pour l'iPad

L'UI est un **reader-first** : layout deux colonnes sur iPad et desktop, plein écran sur mobile.

- Sidebar collapsible avec liste virtualisée (scroll infini)
- Reader épuré, police ajustable (14–22px, persistée)
- Barre de progression de lecture
- Swipe gauche → marquer lu · Swipe droit → bookmark
- Thème sombre natif
- Navigation clavier vim-style

```
j / k      →  article suivant / précédent
r          →  marquer lu / non-lu
b          →  bookmark
o          →  ouvrir l'original
/          →  recherche
[          →  masquer sidebar
?          →  aide
```

---

### Temps réel via SSE

Les nouveaux articles apparaissent **sans recharger la page** grâce aux Server-Sent Events.
Dès qu'un article est scoré, il s'insère en tête de liste — vivant.

---

### PWA — lit aussi hors ligne

MakhalReader s'installe comme une app native sur iPad et iPhone.
Les articles consultés sont mis en cache — accessibles sans réseau.

---

### 32 feeds pré-configurés

L'app démarre avec une sélection technique haute qualité :

| Catégorie | Sources |
|-----------|---------|
| **Infra / Cloud** | Kubernetes Blog, CNCF, Cloudflare, Netflix TechBlog, LWN.net, fasterthanli.me, Fly.io, iximiuz, Tailscale... |
| **AI / LLM** | Anthropic, HuggingFace, Lilian Weng, Sebastian Raschka, Huyen Chip... |
| **Sécurité** | Google Project Zero, PortSwigger, Trail of Bits, lcamtuf, secret.club... |
| **High-signal** | Hacker News, Lobsters, Simon Willison, Julia Evans, Dan Luu... |

Ajout de feeds custom, import **OPML** (Feedly, NewsBlur...), gestion par catégorie.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Caddy (proxy / TLS)               │
└──────────────┬──────────────────────┬───────────────┘
               │                      │
        ┌──────▼──────┐        ┌──────▼──────┐
        │   Frontend   │        │     API      │
        │  React + Vite│        │   FastAPI    │
        │     (PWA)    │        │   SQLite     │
        └─────────────┘        └──────┬───────┘
                                      │
              ┌───────────────────────┼───────────────────┐
              │                       │                   │
       ┌──────▼──────┐        ┌───────▼──────┐   ┌───────▼──────┐
       │   Poller     │        │  Extractor   │   │    Scorer    │
       │  feedparser  │        │ trafilatura  │   │  Gemini via  │
       │  APScheduler │        │ readability  │   │  OpenRouter  │
       └─────────────┘        └─────────────┘   └─────────────┘
```

6 conteneurs Docker · 1 réseau interne · 0 dépendance externe obligatoire

---

## Configuration

```bash
# .env — les seules variables qui comptent

OPENROUTER_API_KEY=sk-or-v1-...       # LLM scoring (gratuit jusqu'à un certain quota)
SCORER_MODEL=google/gemini-2.5-flash-lite   # Modèle utilisé

# Optionnel : Ollama local (fallback si pas d'OpenRouter)
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=mistral

# Fréquence de polling
FETCH_INTERVAL_MINUTES=15

# Guardrails anti-flood
MAX_NEW_ARTICLES_PER_FEED=5
MAX_ARTICLE_AGE_DAYS=7

# Production
CADDY_DOMAIN=reader.mondomaine.com    # Active HTTPS automatique (Let's Encrypt)
```

---

## Déploiement en production

```bash
# Sur ton serveur
git clone <repo> && cd makhalReader
cp .env.example .env && vim .env   # CADDY_DOMAIN + OPENROUTER_API_KEY

docker compose up -d
```

Caddy gère le TLS automatiquement. Rien d'autre à faire.

---

## Stack technique

| Composant | Techno |
|-----------|--------|
| Frontend | React 18 · TypeScript · Vite · Tailwind CSS · Zustand |
| Backend | Python 3.12 · FastAPI · SQLAlchemy · SQLite WAL |
| Extraction | trafilatura · readability · BeautifulSoup |
| Scoring | OpenRouter API (Gemini) · Ollama (Mistral) |
| Infra | Docker Compose · Caddy · APScheduler · httpx async |
| PWA | Workbox · vite-plugin-pwa · Service Workers |

---

<div align="center">

*Fait pour lire moins, comprendre plus.*

</div>
