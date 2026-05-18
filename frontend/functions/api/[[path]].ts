/**
 * Cloudflare Pages Function - Reverse Proxy vers le Backend API
 * 
 * Redirige toutes les requêtes /api/* vers le serveur backend distant (configuré via la variable d'environnement API_BASE_URL).
 * Évite les problèmes de CORS et masque l'URL réelle du backend.
 */

export async function onRequest(context: any) {
  // L'URL de votre backend hébergé (ex: VPS sur Hetzner, Render, Fly.io)
  // À configurer dans le tableau de bord Cloudflare Pages > Paramètres > Variables d'environnement (Production & Preview)
  const backendBase = context.env.API_BASE_URL || "https://api.basira.local";
  
  const incomingUrl = new URL(context.request.url);
  
  // Construit l'URL cible (ex: https://api.basira.local/api/articles?limit=20)
  const targetUrl = new URL(incomingUrl.pathname + incomingUrl.search, backendBase);
  
  // Clone la requête pour l'envoyer au backend
  const requestClone = new Request(targetUrl.toString(), context.request);
  
  // Transfère la requête via l'infrastructure Cloudflare
  const response = await fetch(requestClone);
  
  return response;
}
