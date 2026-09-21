# Pesquisa & Arquitetura de Descoberta Multiplataforma de Vídeos Virais

**Documento:** `docs/multiplatform-video-discovery-research.md`  
**Escopo:** Instagram (Reels/Hashtags/Explore), TikTok (Busca por termo/Hashtag/Trending), YouTube Shorts (Busca por query/Filtro de Shorts/Ordenação por Views).

---

## 1. Resumo Executivo & Matriz de Viabilidade

Para permitir a descoberta automatizada de vídeos virais dentro do **ClippyMe** (buscando por palavra-chave, hashtag ou tema, ranqueando por engajamento/viralidade, extraindo metadados e importando as URLs diretamente para o pipeline de download e cortes), analisamos as opções entre **APIs Oficiais**, **APIs Internas/Reversas Web/Mobile**, **Ferramentas Open-Source** e **Scrapers Dedicados**.

### Matriz de Viabilidade

| Dimensão | Instagram (Reels & Hashtags) | TikTok (Busca & Trending) | YouTube Shorts (Query & Views) |
| :--- | :--- | :--- | :--- |
| **Endpoint Oficial** | Meta Graph API (`/{hashtag-id}/top_media`) | TikTok Research API / Commercial API | YouTube Data API v3 (`search.list` + `videos.list`) |
| **Viabilidade Oficial** | **Muito Baixa (1/5)**<br>• Teto de 30 hashtags únicas por semana<br>• Sem busca por palavra-chave livre<br>• Não retorna contagem de views pública | **Nula para Comercial (0/5)**<br>• Research API restrita a instituições acadêmicas<br>• API comercial não tem busca de descoberta | **Muito Alta (4.5/5)**<br>• Suporta busca livre, duração (`videoDuration=short`) e `order=viewCount`<br>• Cota gratuita diária: 10.000 unidades (100 buscas completas/dia) |
| **Mecanismo Unofficial / Scraper** | Instagram Web GraphQL / Mobile REST (`api/v1/fbsearch/topsearch_flat/`, `instagrapi`) | TikTok Web API (`/api/search/general/full/`) + Assinatura de Tokens | YouTube Innertube API (`/youtubei/v1/search`) / `yt-dlp` (`ytsearch:`) |
| **Defesas Anti-Bot & Autenticação** | • Cookies de Sessão (`sessionid`, `csrftoken`, `mid`)<br>• Headers oficiais (`X-IG-App-ID`)<br>• Desafios de checkpoint / rate limits | • Tokens de Assinatura (`X-Bogus`, `msToken`, `_signature`)<br>• Proteção WAF (Cloudflare/Akamai) | • Praticamente nulo para busca e metadados<br>• yt-dlp nativo resolve streams |
| **Disponibilidade de Views** | ⚠️ Disponível via Scrapers/APIs Web/yt-dlp | ✅ Totalmente disponível | ✅ Totalmente disponível via `videos.list` |
| **URL Direta de Download** | ⚠️ CDN Instagram (expira em ~24h, yt-dlp baixa com cookies) | ✅ CDN TikTok (yt-dlp baixa perfeitamente) | ✅ Totalmente compatível com yt-dlp |
| **Estratégia Recomendada** | **Híbrida**: `instagrapi` / Web GraphQL com sessão de cookies persistida | **Híbrida**: Web API + gerador de assinatura Playwright ou Apify Actor | **API Oficial**: YouTube Data API v3 com fallback para `yt-dlp` |

---

## 2. Detalhamento Técnico por Plataforma

### 2.1 Instagram

#### A. API Oficial (Meta Graph API / Instagram Hashtag API)
* **Fontes Primárias:** [Meta Graph API: Instagram Hashtag Search](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-hashtag-search).
* **Como funciona:**
  1. Converte hashtag para ID: `GET /ig_hashtag_search?q=politica`
  2. Consulta mídias de topo: `GET /{hashtag-id}/top_media?fields=id,caption,media_type,like_count,comments_count,permalink`
* **Limitações Críticas:**
  * **Limite de 30 Hashtags:** Cada conta só pode consultar até 30 hashtags distintas a cada 7 dias móveis.
  * **Sem Contagem de Views:** Não retorna `view_count` ou `play_count` para mídias públicas de terceiros.
  * **Sem Busca por Palavras-Chave Livres:** Apenas hashtags exatas.

#### B. Mecanismo Não Oficial (Web GraphQL & `instagrapi`)
* **Endpoints Internos:**
  * Busca de Termos: `GET https://www.instagram.com/api/v1/fbsearch/topsearch_flat/?query={query}&context=blended`
  * Feed de Hashtag: `GET https://www.instagram.com/api/v1/tags/web_info/?tag_name={tag}`
  * Reels Explore: `POST https://www.instagram.com/api/v1/clips/discover/`
* **Metadados Obtidos:** `play_count` (views), `like_count`, `comment_count`, `taken_at` (data), `caption`, URL do post e miniatura.
* **Mecanismo de Sessão:** O ClippyMe já possui suporte a `cookies.txt` e configuração de credenciais no `data/config.json`. A persistência de sessão evita checkpoints.

---

### 2.2 TikTok

#### A. APIs Oficiais
* **TikTok Research API:** Exclusiva para universidades e ONGs sem fins lucrativos.
* **TikTok Display/Commercial API:** Focada apenas em veiculação de anúncios ou publicação no próprio perfil; não oferece busca aberta de vídeos virais de terceiros.

#### B. Mecanismo Não Oficial (Web Search & Assinaturas)
* **Endpoints Internos:**
  * Busca de Vídeos: `GET https://www.tiktok.com/api/search/general/full/?keyword={keyword}&offset=0&count=20`
* **Assinatura Anti-Bot:**
  * O TikTok exige o cabeçalho/parâmetro `X-Bogus` (token de 28 caracteres gerado via JS `webmssdk.js`) e `msToken`.
* **Solução:**
  * Utilizar um micro-serviço ou worker local em Python/Node (usando Playwright/Chromium leve ou bibliotecas como `TikTok-Api`) para assinar as requisições, obtendo `play_count`, `digg_count` (likes), `share_count` (compartilhamentos) e `comment_count`.

---

### 2.3 YouTube Shorts

#### A. API Oficial (YouTube Data API v3)
* **Fontes Primárias:** [YouTube Data API v3 Search](https://developers.google.com/youtube/v3/docs/search/list).
* **Pipeline em 2 Etapas:**
  1. **Busca:** `GET /search?part=snippet&type=video&videoDuration=short&order=viewCount&q=politica` (Retorna lista de IDs ordenados por relevância ou visualizações).
  2. **Hidratação de Estatísticas:** `GET /videos?part=snippet,statistics,contentDetails&id=ID1,ID2...` (Retorna `viewCount`, `likeCount`, `commentCount`).
* **Vantagens:** Extremamente estável, 100% oficial, sem risco de bloqueio de IP.

#### B. Fallback com `yt-dlp`
* O comando nativo `yt-dlp "ytsearch20:politica" --dump-json` extrai os metadados de 20 vídeos de uma vez sem gastar cota da API.

---

## 3. Algoritmo de Cálculo de Viralidade (Virality Score)

Para comparar vídeos de diferentes plataformas de forma justa, normalizamos os metadados brutos em uma pontuação de **0 a 100**:

```
                               ┌─────────────────────────────┐
                               │     Metadados Brutos        │
                               │  (Views, Likes, Comentários,│
                               │   Shares, Data de Criação)  │
                               └──────────────┬──────────────┘
                                              │
         ┌───────────────────┬────────────────┴──────┬───────────────────┐
         ▼                   ▼                       ▼                   ▼
┌─────────────────┐ ┌──────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  View Velocity  │ │  Taxa Engajamento│ │ Escala de Volume  │ │ Fator Novidade    │
│  (Views / Hora) │ │ (Ponderada p/ rede│ │   (Logarítmica)   │ │  (Decaimento 72h) │
└────────┬────────┘ └────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘
         │                   │                       │                     │
         └───────────────────┼───────────────────────┴─────────────────────┘
                             ▼
              ┌─────────────────────────────┐
              │  Pontuação de Viralidade    │
              │         (0 - 100)           │
              └─────────────────────────────┘
```

### Fórmula:

1. **Idade do Vídeo & Velocidade ($V_{\text{vel}}$):**
   $$\text{Idade}_{\text{horas}} = \max\left(0.5, \frac{T_{\text{atual}} - T_{\text{publicação}}}{3600}\right)$$
   $$V_{\text{vel}} = \frac{\text{Visualizações}}{\text{Idade}_{\text{horas}}}$$

2. **Taxa de Engajamento Ponderada ($\text{ER}$):**
   * **TikTok:** $\text{ER} = \frac{\text{Likes} + 2.5 \cdot \text{Comentários} + 4.0 \cdot \text{Compartilhamentos} + 3.0 \cdot \text{Salvos}}{\text{Views}}$
   * **Instagram:** $\text{ER} = \frac{\text{Likes} + 3.0 \cdot \text{Comentários} + 4.5 \cdot \text{Compartilhamentos}}{\text{Views}}$
   * **YouTube:** $\text{ER} = \frac{\text{Likes} + 3.0 \cdot \text{Comentários}}{\text{Views}}$

3. **Fator de Escala Logarítmica ($S_{\text{vol}}$):**
   Garante que vídeos com milhões de views tenham peso, sem sufocar vídeos novos com alta velocidade:
   $$S_{\text{vol}} = \min\left(1.0, \frac{\log_{10}(\text{Views} + 1)}{6.0}\right)$$

4. **Decaimento por Tempo ($D(t)$ com meia-vida de 72 horas):**
   $$D(t) = \exp(-0.009628 \cdot \text{Idade}_{\text{horas}})$$

5. **Score Final de Viralidade ($S_{\text{viral}} \in [0, 100]$):**
   $$S_{\text{viral}} = 100 \times \left(0.40 \cdot S_{\text{vol}} + 0.35 \cdot \text{EngajamentoRelativo} + 0.25 \cdot \text{VelocidadeRelativa}\right) \times (0.30 + 0.70 \cdot D(t))$$

---

## 4. Arquitetura Proposta para o ClippyMe

```
src/clippyme/domain/discovery/
├── __init__.py                # Exportações
├── schemas.py                 # Schemas Pydantic (DiscoveryItem, SearchQuery, DiscoveryFilter)
├── base.py                    # Interface abstrata DiscoveryProvider
├── scoring.py                 # Cálculo puro e testável do Score de Viralidade
├── cache.py                   # Cache atômico em JSON (data/cache/discovery/)
├── cookie_manager.py          # Gestão de cookies e rotação de sessões
├── providers/
│   ├── youtube_provider.py    # YouTube Data API v3 + fallback ytsearch
│   ├── tiktok_provider.py     # TikTok Web API + Assinador / Scraper
│   └── instagram_provider.py  # Instagram Web GraphQL / instagrapi
└── service.py                 # DiscoveryService (agrega resultados, ordena e filtra)
```

### Integração com o Pipeline de Download Atual:
1. O usuário faz a busca por palavra-chave na interface.
2. O sistema exibe os cards com thumbnail, título, métricas (views, likes) e badge de viralidade.
3. O usuário seleciona os vídeos e clica em **"Importar Selecionados"**.
4. O frontend simplesmente passa as URLs para o endpoint existente (`POST /api/batch` ou `POST /api/viral-studio/batches`).
5. O pipeline de download (`yt-dlp`), transcrição e IA continua operando sem nenhuma alteração estrutural.
