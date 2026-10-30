# MakhalReader sur Kubernetes

Manifests vanilla (pas de Helm, pas d'Ingress, pas de TLS). Le proxy `web` est
expose par un `Service` de type `LoadBalancer` sur le port 80 en HTTP.

## Contenu

| Fichier | Ressources |
|---|---|
| `00-namespace.yaml` | Namespace `makhal-reader` |
| `01-configmap.yaml` | Configuration non sensible partagee par les services |
| `02-secret.yaml` | `AUTH_PASSWORD`, `API_SECRET`, cles LLM |
| `10-api.yaml` | PVC SQLite, Deployment `api`, Service `api:8000` |
| `20-extractor.yaml` | Deployment `extractor`, Service `extractor:8001` |
| `30-scorer.yaml` | Deployment `scorer`, Service `scorer:8002` |
| `40-poller.yaml` | Deployment `poller` (un seul replica) |
| `50-frontend.yaml` | Deployment `frontend`, Service `frontend:80` |
| `60-web.yaml` | Config nginx, Deployment `web`, Service LoadBalancer `web:80` |

Les noms des Services (`api`, `extractor`, `scorer`, `frontend`) sont un contrat
dur : `poller` et `scorer` appellent `http://api:8000`, et le nginx de `web`
route vers `api:8000` / `frontend:80`. Les renommer casse l'application.

## 1. Construire et publier les images

Cinq images sont necessaires. Depuis la racine du depot :

```bash
docker build -t makhal-reader/api:latest       backend/api
docker build -t makhal-reader/extractor:latest backend/extractor
docker build -t makhal-reader/scorer:latest    backend/scorer
docker build -t makhal-reader/poller:latest    backend/poller
docker build -t makhal-reader/frontend:latest  frontend
```

Avec un registre, prefixez par son adresse puis poussez :

```bash
REGISTRY=registry.example.com
for img in api extractor scorer poller frontend; do
  docker tag "makhal-reader/$img:latest" "$REGISTRY/makhal-reader/$img:latest"
  docker push "$REGISTRY/makhal-reader/$img:latest"
done
```

Adaptez les champs `image:` des manifests (ou utilisez
`kubectl -n makhal-reader set image`). Pour un cluster local :

```bash
# kind
kind load docker-image makhal-reader/api:latest --name <cluster>
# minikube
minikube image load makhal-reader/api:latest
```

`imagePullPolicy: IfNotPresent` : pour deployer une nouvelle version, utilisez
un tag explicite (`:v2`, commit SHA) ou rechargez l'image dans le cluster.

## 2. Configurer le secret

Editez `k8s/02-secret.yaml` avant le premier deploiement :

- `AUTH_PASSWORD` : obligatoire, mot de passe de connexion.
- `API_SECRET` : secret interne partage par `api`, `poller` et `scorer`.
- `OPENROUTER_API_KEY` / `LLM_API_KEY` : optionnels, selon le provider LLM.

Pour du HTTP sans TLS, `HTTPS_ONLY=false` est deja positionne dans le
ConfigMap : le cookie de session n'est pas marque `Secure`. N'exposez pas ce
LoadBalancer sur Internet sans ajouter TLS devant.

Provider LLM : renseignez `OPENROUTER_API_KEY`, ou `LLM_BASE_URL` /
`LLM_API_KEY` / `LLM_MODEL` dans le ConfigMap/Secret pour un endpoint
OpenAI-compatible. Pour un Ollama dans le cluster, mettez `OLLAMA_URL` a
l'adresse de son Service (par exemple
`http://ollama.ollama.svc.cluster.local:11434`). Sans provider configure, le
scoring et les fonctions LLM echouent proprement ; le reste de l'application
fonctionne.

## 3. Deployer

```bash
kubectl apply -f k8s/
```

Verifier :

```bash
kubectl -n makhal-reader get pods,svc,pvc
kubectl -n makhal-reader get svc web -w   # attendre EXTERNAL-IP
curl http://<EXTERNAL-IP>/api/health
```

`EXTERNAL-IP` reste `<pending>` si le cluster n'a pas d'implementation
LoadBalancer (MetalLB, LB cloud, k3s servicelb…). `kubectl port-forward` permet
de diagnostiquer mais ne remplace pas le LoadBalancer demande.

Logs :

```bash
kubectl -n makhal-reader logs deploy/api
kubectl -n makhal-reader logs deploy/poller
```

## 4. Deployer avec ArgoCD

ArgoCD applique le contenu de `k8s/` depuis Git : il ne construit pas les
images. Les manifests doivent etre commites, et les images poussees dans un
registre accessible par les noeuds (voir etape 1). Le modele est une
`Application` unique, pas un App of Apps.

Prerequis : ArgoCD installe dans le cluster et un depot Git accessible par
ArgoCD.

### Manifest Application

Placez ce fichier **hors de `k8s/`**, par exemple dans
`argocd/makhal-reader.yaml` : dans `k8s/`, ArgoCD essaierait de gerer sa propre
ressource `Application` dans le namespace applicatif.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: makhal-reader
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/<org>/<repo>.git
    targetRevision: main
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: makhal-reader
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

```bash
mkdir -p argocd
# enregistrez le manifeste ci-dessus dans argocd/makhal-reader.yaml
kubectl apply -f argocd/makhal-reader.yaml
```

Equivalent en CLI ArgoCD :

```bash
argocd app create makhal-reader \
  --repo https://github.com/<org>/<repo>.git \
  --path k8s \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace makhal-reader \
  --sync-policy automated \
  --auto-prune \
  --self-heal \
  --sync-option CreateNamespace=true
```

Verification :

```bash
argocd app get makhal-reader
argocd app diff makhal-reader
argocd app sync makhal-reader          # sync immediat si l'auto-sync tarde
argocd app wait makhal-reader --health
kubectl -n makhal-reader get pods,svc,pvc
kubectl -n makhal-reader get svc web -w
```

ArgoCD cree les ressources dans l'ordre Namespace, ConfigMap/Secret, Services,
puis Deployments : le nginx de `web` peut resoudre `api` et `frontend` des son
demarrage.

### Depot Git prive

```bash
argocd repo add https://github.com/<org>/<repo>.git \
  --username <user> --password <token>
```

Pour SSH, utilisez l'URL `git@github.com:<org>/<repo>.git` dans `repoURL` et :

```bash
argocd repo add git@github.com:<org>/<repo>.git \
  --ssh-private-key-path ~/.ssh/id_ed25519
```

### Secret et donnees sensibles

`02-secret.yaml` est dans le chemin synchronise : ArgoCD applique les valeurs
presentes dans Git, et `selfHeal` reecrit toute modification manuelle du Secret
au prochain sync.

- Depot prive : mettez les vraies valeurs dans `02-secret.yaml`.
- Depot public : ne committez jamais les vraies valeurs. Remplacez le Secret
  par un `SealedSecret`, un `ExternalSecret` ou un manifeste SOPS avant de
  creer l'Application.

Un changement de Secret ou de ConfigMap ne relit pas les variables des
conteneurs deja demarres. Supprimez les pods concernes (preferable a
`kubectl rollout restart` avec `selfHeal`, qui peut annuler l'annotation de
redemarrage) :

```bash
for c in api extractor scorer poller web; do
  kubectl -n makhal-reader delete pod -l app.kubernetes.io/component=$c
done
```

### Mettre a jour les images

ArgoCD ne reconstruit rien. Construisez et poussez une image avec un tag
immuable, mettez a jour les champs `image:` dans Git, puis commitez : le sync
deploie le nouveau tag.

```bash
docker build -t registry.example.com/makhal-reader/api:v1.2.3 backend/api
docker push registry.example.com/makhal-reader/api:v1.2.3
# puis image: registry.example.com/makhal-reader/api:v1.2.3 dans k8s/10-api.yaml
```

Evitez `:latest` avec `imagePullPolicy: IfNotPresent` : si le tag ne change pas,
aucun rollout n'est declenche et un noeud peut conserver l'ancienne image.
ArgoCD Image Updater peut automatiser la mise a jour des tags.

Registre prive : les identifiants Git d'ArgoCD ne servent pas a tirer les
images. Ajoutez un pull secret au ServiceAccount du namespace, par exemple :

```bash
kubectl -n makhal-reader create secret docker-registry regcred \
  --docker-server=registry.example.com \
  --docker-username=<user> --docker-password=<token>
kubectl -n makhal-reader patch serviceaccount default \
  -p '{"imagePullSecrets":[{"name":"regcred"}]}'
```

### Protection du volume SQLite

Le PVC porte l'annotation `argocd.argoproj.io/sync-options: Prune=false` : si
`10-api.yaml` disparait du depot, ArgoCD ne supprime pas le volume. En revanche,
une suppression de l'Application avec cascade supprime les ressources ; pour ne
supprimer que l'Application et conserver les donnees :

```bash
argocd app delete makhal-reader --cascade=false
```

### Depannage ArgoCD

```bash
argocd app diff makhal-reader
argocd app history makhal-reader
argocd app rollback makhal-reader <revision-id>
kubectl -n argocd logs deploy/argocd-application-controller
```

- `OutOfSync` sur le Secret : modification manuelle (annulee par `selfHeal`) ou
  valeurs non commitees.
- `ImagePullBackOff` : tag absent du registre ou pull secret manquant.
- `EXTERNAL-IP: <pending>` : aucune implementation LoadBalancer dans le
  cluster, voir la section 3.

## Contraintes

- **API en un seul replica** : SQLite sur un PVC `ReadWriteOnce`, strategie
  `Recreate`. Ne scalez pas `api` horizontalement.
- **Poller en un seul replica** : deux pollers declencheraient des ingestions
  en double.
- Le PVC `makhal-reader-data` (10 Gi) utilise la StorageClass par defaut du
  cluster. Ajustez la taille ou `storageClassName` si necessaire. Les donnees
  existantes ne sont pas migrees automatiquement depuis le volume Docker.
- `scorer` et `poller` n'ont pas besoin de DNS externe particulier, mais
  l'extraction et le scoring necessitent un acces reseau sortant (RSS, LLM).
- Tout est dans le namespace `makhal-reader` : les noms courts entre Services
  en dependent.
