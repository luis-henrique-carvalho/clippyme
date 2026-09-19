Documento de planejamento
Versão: 1.0
Projeto: ClippyMe
Módulo: Viral Content Studio
Finalidade: Automação de vídeos de achadinhos e conteúdo de afiliados.
Repositório local: /home/luis/repositories/clippyme
Status: Especificação para implementação futura. Nenhuma alteração de código foi realizada.
O Viral Content Studio será um novo módulo do ClippyMe destinado à produção automatizada de vídeos curtos para perfis de achadinhos, recomendações de produtos e marketing de afiliados.
A funcionalidade permitirá ao usuário fornecer URLs de vídeos do Instagram Reels e TikTok, associar cada vídeo a um produto e selecionar a marca responsável pela publicação.
O ClippyMe deverá baixar os vídeos, analisar seu conteúdo por meio de inteligência artificial, gerar frases comerciais contextualizadas e aplicar automaticamente um template visual contendo identidade da marca, headline e marca-d'água.
Após a renderização, os conteúdos deverão ficar disponíveis para revisão, edição de textos, agendamento e publicação utilizando a infraestrutura já existente no projeto.
Princípio arquitetural: o Viral Content Studio não deve recriar funcionalidades já existentes no ClippyMe. Deve funcionar como um novo fluxo de negócio que reutiliza os serviços atuais de download, inteligência artificial, composição audiovisual, processamento assíncrono e publicação.
Automatizar a transformação de vídeos demonstrativos de diferentes produtos em conteúdos personalizados para publicação em redes sociais.
O usuário deverá conseguir executar o fluxo:
Selecionar marca
Adicionar URLs dos vídeos e dados dos produtos
Iniciar processamento do lote
Download + análise por IA
Geração de headlines e legendas
Aplicação do template visual
Renderização dos vídeos
Revisão dos resultados
Publicação ou agendamento
- Permitir o gerenciamento de múltiplas marcas e perfis de publicação.
- Padronizar visualmente todos os vídeos de uma marca.
- Reduzir o trabalho manual de edição.
- Produzir textos comerciais específicos para cada produto.
- Permitir o processamento de lotes com quantidade variável de vídeos.
- Reutilizar os componentes existentes do ClippyMe.
- Preservar a compatibilidade com o pipeline original de geração de cortes.
- Preparar a arquitetura para integração futura com um Radar de Reels virais.
Funcionalidade
Escopo
Gerenciamento de marcas
Incluído
Logo e identidade por marca
Incluído
Entrada por URLs
Incluído
Upload manual de mídia
Alternativa de ingestão
Instagram Reels
Incluído
TikTok
Incluído
Lotes sem limite fixo de quatro vídeos
Incluído
Código individual do produto
Incluído
Link individual opcional
Incluído
Link padrão da marca
Incluído
Download de vídeos
Incluído
Análise com Gemini
Incluído
Geração de headlines
Incluído
Geração de legendas
Incluído
Template visual
Incluído
Renderização em MP4
Incluído
Revisão individual
Incluído
Publicação via integração existente
Incluído
As seguintes funcionalidades deverão permanecer fora da primeira versão:
- Monitoramento automático de perfis de concorrentes.
- Ranking de Reels por visualizações.
- Integração com Instagram Outlier.
- Identificação de produtos virais em múltiplos perfis.
- Pesquisa automática de produtos na Shopee, Mercado Livre ou SHEIN.
- Geração automática de links individuais de afiliados.
- Importação automática de imagens e vídeos dos marketplaces.
- Automação de mensagens privadas a partir de comentários.
- Análise de comissões, vendas e conversões.
A arquitetura deverá permitir a incorporação dessas funcionalidades posteriormente sem exigir a reconstrução do Viral Content Studio.
O Viral Content Studio deverá utilizar os serviços existentes sempre que forem compatíveis com os novos requisitos.
O plano identifica os seguintes arquivos como pontos candidatos de integração.
Responsabilidade
Arquivo existente indicado
Download
src/clippyme/pipeline/download.py
Gemini
src/clippyme/pipeline/gemini_request.py
Análise e edição por IA
src/clippyme/domain/clip_edit_ai.py
Fontes e textos
src/clippyme/domain/hooks.py
Logo
src/clippyme/domain/logo.py
Composição
src/clippyme/domain/compose.py
Codificação
src/clippyme/domain/encode.py
Publicação
src/clippyme/integrations/social_publisher.py
Dashboard
dashboard/src/RedesignApp.jsx
Nota de implementação: estes são os pontos de integração identificados no planejamento. Antes de desenvolver, deve-se confirmar na cópia local as assinaturas, responsabilidades e dependências reais de cada componente.
Não se deve presumir que todos os serviços existentes possam ser reutilizados integralmente sem adaptações.
Pipeline tradicional
Vídeo longo
↓
Análise
↓
Seleção de cortes
↓
Edição
↓
Publicação
Viral Content Studio
Reel ou TikTok
↓
Análise comercial
↓
Aplicação de template
↓
Renderização
↓
Publicação
Infraestrutura compartilhada
Download · Gemini · FFmpeg · Processamento assíncrono · Dashboard · Publicação
O novo módulo não deverá executar automaticamente detecção de momentos virais, seleção de novos cortes ou reframing quando o objetivo for preservar o vídeo demonstrativo original.
O sistema deverá permitir cadastrar e gerenciar múltiplas marcas.
Uma marca representa uma identidade visual e comercial utilizada na produção dos conteúdos.
Exemplos:
- Vale o Clique?
- Ofertas da Florzinha
- Outros perfis de achadinhos administrados pelo usuário.
Cada marca deverá possuir:
Campo
Descrição
id
Identificador interno
name
Nome de exibição
handle
Nome de usuário nas redes
avatar_path
Imagem circular do perfil
logo_path
Logotipo oficial
default_cta
Chamada comercial padrão
default_affiliate_url
Link padrão de afiliado
template_id
Template visual selecionado
publishing_profiles
Perfis de publicação vinculados
created_at
Data de criação
updated_at
Data da última alteração
A imagem de avatar e o logotipo deverão ser campos independentes.
Ao selecionar uma marca, o Viral Studio deverá carregar automaticamente:
- Logo e avatar.
- Nome de exibição.
- Handle.
- Template visual.
- CTA padrão.
- Link de afiliado.
- Perfis sociais vinculados para publicação.
O usuário poderá editar esses dados por meio da opção Gerenciar Marcas.
A proposta inicial é utilizar:
data/viral_studio_accounts.json
Entretanto, antes da implementação deverá ser verificado se o ClippyMe já possui um mecanismo persistente de configurações que possa ser reaproveitado.
Não deverá ser introduzido um novo banco de dados exclusivamente para armazenar essas configurações.
O usuário deverá acessar a aba Viral Studio e selecionar a marca responsável pelo conteúdo.
Em seguida, poderá adicionar uma quantidade variável de vídeos.
Não haverá limite funcional fixo de quatro vídeos por lote.
O usuário poderá adicionar novos itens dinamicamente e remover entradas antes de iniciar o processamento.
Cada vídeo representará um produto diferente.
Campo
Obrigatório
Descrição
URL do vídeo ou upload
Sim
Mídia de origem
Código do produto
Não
Identificador comercial
Link do produto
Não
URL individual de afiliado
Headline manual
Não
Substituição opcional da geração automática
Instrução adicional
Não
Orientação específica para a IA
Exemplo:
```
{
  "brand_id": "vale-o-clique",
  "items": [
    {
      "source_url": "https://instagram.com/reel/AAA/",
      "product_code": "2567",
      "product_url": null
    },
    {
      "source_url": "https://instagram.com/reel/BBB/",
      "product_code": "2568",
      "product_url": null
    },
    {
      "source_url": "https://tiktok.com/@perfil/video/123",
      "product_code": "2569",
      "product_url": null
    }
  ]
}
```
As URLs acima são ilustrativas.
Além da inclusão manual de linhas, a interface deverá permitir colar múltiplas URLs de uma vez.
A quantidade de entradas não deve depender de um número fixo de campos no frontend.
Não estabelecer um limite fixo de quatro vídeos não significa permitir execução simultânea irrestrita.
O sistema deverá respeitar os limites de concorrência, armazenamento, requisições e processamento já existentes no ClippyMe.
Lotes grandes deverão ser processados progressivamente, sem exigir que todas as mídias sejam carregadas em memória ao mesmo tempo.
Obter os arquivos audiovisuais informados pelo usuário e disponibilizá-los ao pipeline de composição.
Arquivo candidato:
src/clippyme/pipeline/download.py
Reutilizar:
- yt-dlp.
- Controle de timeout.
- Sanitização de nomes.
- Tratamento de erros.
- Organização de arquivos.
- Normalização de formatos, quando disponível.
Adicionar suporte às URLs de:
- Instagram Reels.
- TikTok.
A validação deverá aceitar os domínios legítimos e os formatos de URL compatíveis.
A simples inclusão de domínios em uma lista de hosts não garante que os downloads funcionarão. O comportamento real deverá ser testado.
O sistema deverá identificar situações como:
- Vídeo indisponível.
- Autenticação necessária.
- URL inválida.
- Conteúdo removido.
- Falha de rede.
- Timeout.
- Limitação de requisições.
Quando o download falhar, o usuário deverá poder reenviar a tarefa ou fornecer o arquivo manualmente.
O vídeo original deverá ser preservado separadamente da versão renderizada.
Reprocessamentos de headline, template ou legenda não deverão exigir um novo download quando o arquivo original estiver disponível.
A origem e a permissão de reutilização deverão ser registradas. Vídeos de terceiros obtidos para análise não deverão ser automaticamente considerados autorizados para publicação comercial.
Analisar cada vídeo individualmente e gerar conteúdo comercial correspondente ao produto apresentado.
Arquivos candidatos:
```
src/clippyme/pipeline/gemini_request.py
src/clippyme/domain/clip_edit_ai.py
```
Reutilizar, quando compatível:
- Inicialização do Gemini.
- Configuração de modelo.
- Tratamento de respostas.
- Parsing de JSON.
- Controle de erros.
- Contabilização de tokens e custos.
Adicionar uma operação especializada:
generate_affiliate_copy
Ela não deverá utilizar diretamente o prompt de seleção de cortes do ClippyMe.
O objetivo será compreender o produto e produzir textos comerciais.
A operação receberá:
- Frames representativos do vídeo ou vídeo completo.
- Transcrição do áudio, quando disponível.
- Legenda original, quando disponível.
- Nome da marca.
- Tom de voz da marca.
- Código do produto.
- CTA padrão.
- Instruções adicionais do usuário.
```
{
  "product": "Organizador de cozinha",
  "product_description": "Organizador expansível para armários",
  "headlines": [
    "Quem tem cozinha pequena precisa conhecer isso!",
    "Olha como aproveitar melhor esse espaço!",
    "Esse organizador pode transformar seu armário!"
  ],
  "selected_headline": "Quem tem cozinha pequena precisa conhecer isso!",
  "caption": "Uma solução prática para organizar sua cozinha. Confira os achadinhos no link da bio!",
  "hashtags": [
    "#achadinhos",
    "#organizacao",
    "#cozinha",
    "#publi"
  ]
}
```
A IA deverá:
- Gerar cinco opções por vídeo.
- Utilizar português brasileiro.
- Priorizar frases curtas.
- Destacar o benefício demonstrado.
- Despertar curiosidade.
- Respeitar a identidade da marca.
- Evitar repetir sistematicamente os mesmos ganchos.
- Não inventar funcionalidades, preços ou descontos.
A headline deverá ser editável antes e depois da primeira renderização.
A legenda poderá conter:
1. Gancho inicial.
2. Descrição curta do produto.
3. Benefício demonstrado.
4. CTA.
5. Código do produto, quando informado.
6. Hashtags.
Exemplo:
Quem tem cozinha pequena precisa ver isso! 😱
Esse organizador ajuda a aproveitar melhor os espaços do armário e deixar tudo mais organizado.
📌 Produto 2567
Confira os achadinhos no link da bio!
#achadinhos #cozinha #organizacao #publi
A IA não deverá inventar códigos, intervalos de destaques, URLs ou comissões.
Chamadas como "Comente QUERO que eu envio no direct" deverão ser utilizadas somente quando existir um processo configurado para atender aos comentários. A publicação pelo Zernio não deve ser confundida com automação de mensagens privadas.
Os resultados da IA deverão ser armazenados.
Alterações no template não deverão gerar uma nova chamada à IA.
Alterações na legenda não deverão exigir reanálise do vídeo.
Transformar o vídeo demonstrativo em um conteúdo visualmente padronizado, utilizando a identidade da marca selecionada.
Arquivos candidatos:
```
src/clippyme/domain/hooks.py
src/clippyme/domain/logo.py
src/clippyme/domain/compose.py
src/clippyme/domain/encode.py
```
As rotinas existentes de imagem, fontes, composição e codificação deverão ser reutilizadas quando adequadas.
O primeiro template deverá seguir o formato de referência enviado pelo usuário:
Especificação visual
VALE O CLIQUE?
@valeoclique
Quem tem cozinha pequena precisa conhecer isso! 😱
@valeoclique
Representação conceitual. O template será construído com os arquivos visuais oficiais da marca.
Propriedade
Valor inicial
Resolução
1080 × 1920
Proporção
9:16
Formato
MP4
Fundo
Branco
Logo/avatar
Região superior esquerda
Nome da marca
Ao lado do avatar
Handle
Abaixo do nome
Headline
Acima do vídeo
Vídeo
Centralizado na região disponível
Marca-d'água
Sobre o vídeo, em posição configurável
Coordenadas de referência:
```
Canvas: 1080 × 1920

Avatar:
x = 60
y = 80

Nome:
à direita do avatar

Handle:
abaixo do nome

Headline:
abaixo do cabeçalho

Vídeo:
centralizado na área útil restante
```
As coordenadas são valores iniciais. O motor deverá calcular o espaço disponível considerando a altura real da headline e as dimensões da mídia.
O renderizador deverá:
- Preservar o vídeo integral sempre que possível.
- Preservar o áudio original.
- Evitar distorções de proporção.
- Suportar vídeos verticais, horizontais e quadrados.
- Realizar quebra automática de linhas.
- Ajustar a fonte quando necessário.
- Suportar caracteres acentuados e emojis.
- Respeitar margens de segurança.
- Evitar que os elementos visuais cubram o produto.
- Preservar marcas de autoria de terceiros.
Quando o material original não for vertical, o comportamento deverá ser definido pelo template, utilizando preenchimento, enquadramento ou barras conforme a configuração, sem eliminar automaticamente informações importantes.
O layout não deverá ficar rigidamente vinculado ao Vale o Clique?.
Cada marca deverá poder selecionar um template com configurações próprias.
```
{
  "template_id": "classic-affiliate",
  "width": 1080,
  "height": 1920,
  "background_color": "#FFFFFF",
  "avatar_enabled": true,
  "brand_name_enabled": true,
  "headline_enabled": true,
  "watermark_enabled": true,
  "video_fit": "contain"
}
```
Alterações no template deverão permitir nova renderização sem novo download ou nova análise da IA.
O Viral Content Studio deverá utilizar o padrão de processamento assíncrono já existente no ClippyMe.
Não implementar um novo gerenciador de jobs, uma nova fila independente ou outro mecanismo de concorrência se os componentes atuais já atenderem aos requisitos.
Não haverá limite funcional fixo de quatro vídeos.
O usuário poderá criar lotes com diferentes quantidades de produtos.
Exemplos:
- 1 vídeo.
- 5 vídeos.
- 20 vídeos.
- 50 vídeos.
- Quantidades maiores, conforme os recursos disponíveis.
A quantidade de vídeos por lote não deve determinar quantos vídeos serão processados simultaneamente.
A concorrência deverá ser controlada pela infraestrutura existente.
Cada produto deverá possuir seu próprio resultado de processamento dentro do lote.
Se um vídeo falhar, os demais deverão continuar conforme o comportamento suportado pelo gerenciador de jobs existente.
Não deverão ser descartados resultados concluídos por causa de uma falha em outro item.
Reutilizar os estados atuais sempre que representarem adequadamente o novo fluxo.
Estados conceituais necessários:
```
PENDING
DOWNLOADING
ANALYZING
RENDERING
READY_FOR_REVIEW
APPROVED
SCHEDULED
PUBLISHED
FAILED
CANCELLED
```
Não é necessário criar todos esses estados literalmente caso já existam equivalentes no ClippyMe.
O sistema deverá permitir:
- Repetir um download que falhou.
- Reexecutar análise com IA.
- Gerar novas headlines.
- Renderizar novamente com outra headline.
- Alterar o template.
- Editar a legenda.
- Reenviar uma publicação que falhou.
Cada operação deverá reutilizar os resultados anteriores quando possível.
Uma tentativa repetida de publicação não deverá criar posts duplicados acidentalmente.
Após o processamento, o sistema deverá apresentar os vídeos individualmente.
Cada resultado deverá possuir:
- Player de vídeo.
- Nome da marca.
- Produto identificado.
- Código do produto.
- URL original.
- Headline selecionada.
- Outras headlines geradas.
- Legenda editável.
- Hashtags.
- Link comercial.
- Status de processamento.
- Status de autorização de uso.
- Ações de renderização e publicação.
O usuário poderá:
- Reproduzir o vídeo.
- Alterar a headline.
- Editar a legenda.
- Alterar o código do produto.
- Alterar o link.
- Gerar novas headlines.
- Renderizar novamente.
- Aprovar.
- Agendar.
- Publicar.
O usuário poderá selecionar vários resultados para:
- Aplicar um template.
- Aprovar conteúdos.
- Agendar.
- Publicar.
- Exportar os arquivos.
A aprovação e a publicação em lote deverão respeitar o estado e as permissões de cada item.
Não haverá geração automática de links de afiliados na primeira versão.
O usuário poderá configurar um link padrão para cada marca e informar links específicos para produtos individuais.
A regra deverá ser:
```
Se existe link individual do produto:
    utilizar link individual

Caso contrário:
    utilizar link padrão da marca
```
O código será informado manualmente.
Exemplo:
```
Produto 2567
```
Esse código poderá ser inserido automaticamente na legenda.
Não deverá ser inventado pela IA.
Editar o link ou o código do produto não deverá exigir nova renderização, exceto quando o usuário optar por incluir essas informações visualmente dentro do vídeo.
Arquivo candidato:
src/clippyme/integrations/social_publisher.py
O Viral Studio deverá utilizar o mecanismo de publicação já existente no ClippyMe.
Não desenvolver uma segunda integração com Instagram, TikTok ou YouTube quando a atual puder ser reutilizada.
```
Vídeo renderizado
      ↓
Revisão
      ↓
Aprovação
      ↓
Seleção das plataformas
      ↓
Publicar agora ou agendar
      ↓
Integração existente
      ↓
Registro do resultado
```
A publicação deverá considerar:
- Marca selecionada.
- Conta social vinculada.
- MP4 final.
- Legenda.
- Hashtags.
- Link comercial.
- Horário de publicação.
- Status retornado pelo provedor.
O usuário deverá conseguir publicar apenas parte dos conteúdos de um lote.
O sistema deverá registrar os identificadores retornados pelo provedor e evitar publicações duplicadas.
O reaproveitamento do SmartScheduler, caso disponível na versão local, deverá respeitar suas regras de concorrência e prevenção de colisões de horários.
As entidades abaixo representam responsabilidades de negócio. Não são uma exigência de criar novas tabelas ou arquivos caso o ClippyMe já tenha estruturas equivalentes.
Identidade visual e comercial.
Agrupamento dos vídeos enviados em uma operação.
Produto e vídeo individuais dentro do lote.
Análise, headlines, legenda e hashtags.
Configurações visuais da marca.
Arquivo final e metadados de renderização.
Destino, agendamento e estado de publicação.
```
erDiagram
    BRAND ||--o{ VIRAL_BATCH : creates
    BRAND ||--o{ TEMPLATE : owns
    VIRAL_BATCH ||--|{ VIRAL_ITEM : contains
    VIRAL_ITEM ||--o{ AI_CONTENT : generates
    VIRAL_ITEM ||--o{ RENDERED_MEDIA : produces
    TEMPLATE ||--o{ RENDERED_MEDIA : configures
    RENDERED_MEDIA ||--o{ PUBLICATION : publishes
```
A entidade de item deverá manter identidade própria independentemente da quantidade de vídeos no lote.
Os endpoints definitivos deverão seguir o padrão de rotas e autenticação existente no ClippyMe.
Sugestão de contratos:
Método
Endpoint
Responsabilidade
GET
/api/viral-studio/brands
Listar marcas
POST
/api/viral-studio/brands
Criar marca
PATCH
/api/viral-studio/brands/{id}
Atualizar marca
GET
/api/viral-studio/templates
Listar templates
POST
/api/viral-studio/batches
Criar lote
GET
/api/viral-studio/batches/{id}
Consultar lote
GET
/api/viral-studio/items/{id}
Consultar vídeo
PATCH
/api/viral-studio/items/{id}
Editar dados comerciais
POST
/api/viral-studio/items/{id}/render
Renderizar novamente
POST
/api/viral-studio/items/{id}/approve
Aprovar conteúdo
POST
/api/viral-studio/publish
Enviar para publicação
Esses contratos deverão ser adaptados caso o ClippyMe possua endpoints equivalentes que possam ser estendidos.
Categoria
Requisito
Compatibilidade
Não quebrar o pipeline tradicional
Reutilização
Priorizar componentes existentes
Escalabilidade
Suportar lotes de tamanho variável
Concorrência
Reutilizar controles atuais
Persistência
Preservar estado de jobs e resultados
Resiliência
Isolar falhas entre vídeos
Idempotência
Evitar processamento e publicação duplicados
Cache
Reutilizar vídeos e análises
Segurança
Proteger credenciais e arquivos
Observabilidade
Disponibilizar progresso e logs
UX
Permitir revisão e edição individual
Qualidade
Validar integridade dos MP4
Custo
Evitar chamadas redundantes à IA
URLs fornecidas pelo usuário deverão ser validadas para evitar acesso indevido a endereços internos ou protocolos não permitidos. Arquivos e parâmetros do FFmpeg também deverão ser sanitizados.
Credenciais, cookies e tokens não deverão aparecer nos logs ou ser armazenados em configurações públicas do frontend.
O módulo será considerado funcional quando atender aos seguintes cenários.
Checklist de implementação futura
Todos os critérios estão inicialmente pendentes. Esta lista não representa testes executados.
Gerenciamento de marcas
Cadastrar uma marca com nome, handle, avatar e logo.
Salvar CTA e link padrão.
Selecionar a marca no Viral Studio.
Carregar o template e perfil de publicação correspondentes.
Entrada de conteúdo
Adicionar uma quantidade variável de URLs.
Associar códigos individuais aos produtos.
Informar links específicos opcionais.
Remover e adicionar vídeos antes de iniciar.
Pipeline audiovisual
Baixar os vídeos acessíveis.
Preservar os arquivos originais.
Gerar conteúdo comercial individual com IA.
Aplicar o template da marca.
Exportar arquivos MP4 válidos.
Processamento
Reutilizar o sistema de jobs existente.
Manter resultados concluídos quando outro item falhar.
Reprocessar falhas individualmente.
Alterar headline sem repetir o download.
Renderizar novamente sem reanálise desnecessária.
Publicação
Revisar cada vídeo.
Selecionar headlines e editar legendas.
Associar o link comercial correto.
Aprovar conteúdos autorizados.
Publicar ou agendar pelas integrações existentes.
Registrar o resultado sem duplicidade.
A implementação deverá ser incremental.
Fase
Entrega
1
Inspeção e mapeamento dos componentes existentes
2
Cadastro de marcas e configuração de templates
3
Ingestão de um vídeo
4
Análise comercial com IA
5
Renderização do template
6
Integração com jobs e lotes
7
Dashboard de revisão
8
Integração com publicação
9
Testes de regressão do ClippyMe
A integração com o Radar de Reels virais ficará para uma evolução posterior.
1. Não reinventar a infraestrutura.
Reutilizar o gerenciador de jobs, download, IA, FFmpeg e publicação do ClippyMe sempre que forem compatíveis.
2. Não limitar artificialmente a quantidade de vídeos.
O frontend deverá aceitar lotes de tamanho variável. A infraestrutura determinará a concorrência operacional.
3. Tratar cada vídeo como um produto individual.
Headlines, legendas, códigos, links e arquivos finais pertencem ao item, não ao lote inteiro.
4. Separar as etapas de processamento.
Download, análise, renderização e publicação deverão permitir reaproveitamento independente de seus resultados.
5. Manter as marcas configuráveis.
Nenhum nome, logo, handle, CTA ou cor do Vale o Clique? deverá ficar rigidamente definido no renderizador.
6. Preservar o ClippyMe original.
A nova funcionalidade não deverá comprometer o pipeline existente de geração de cortes.
7. Preparar a arquitetura para descoberta automática.
O Viral Studio deverá aceitar futuramente vídeos selecionados por um Radar de Reels, sem exigir mudanças no pipeline de produção.
Ao finalizar o MVP, o usuário deverá conseguir abrir o ClippyMe, acessar o Viral Content Studio, selecionar uma marca, adicionar diversos vídeos de produtos diferentes e iniciar a geração do lote.
O sistema deverá produzir um vídeo personalizado para cada item, com sua própria headline, legenda, código e link comercial, utilizando a identidade visual da marca selecionada.
Os vídeos deverão ficar disponíveis para revisão e publicação utilizando as funcionalidades existentes do ClippyMe.
A entrega final do módulo será uma nova experiência de produção de conteúdo dentro do ClippyMe, e não uma aplicação separada, um novo motor de edição ou um segundo sistema de processamento assíncrono.