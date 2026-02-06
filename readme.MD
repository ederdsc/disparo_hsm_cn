# Sistema de Disparo HSM 

Este projeto tem como objetivo semi-automatizar o disparo de mensagens HSM informativas via WhatsApp, com o intuito de deixar os clientes cientes se estão sendo afetados por algum rompimento ou massiva afetando sua conexão.


## Tabela de conteúdos

- [Arquitetura](#arquitetura)
- [Features](#features)
- [Instruções de execução](#instruções-de-execução)

## Arquitetura

O projeto segue uma arquitetura monolítica leve, conteinerizada para fácil deploy, focada em performance para chamadas de API.

![Architecture Diagram](./images/architecture_diagram.png)

**Python & Flask**

*Utilizei Flask pela sua leveza e flexibilidade. Como o núcleo da aplicação é receber um webhook/polling, processar dados e disparar ações, o Python se mostrou excelente. Implementei um `ThreadPoolExecutor` para processar centenas de clientes em paralelo, reduzindo o tempo de carregamento dos detalhes de 40s para menos de 3s.*

**Persistência JSON (Lightweight)**

*Para manter a aplicação portátil e sem dependência de bancos de dados pesados para essa versão, utilizei persistência em arquivos JSON locais para Logs de Auditoria e Controle de Cooldown (Flap Damping). Isso simplifica o backup e a migração de ambientes.*

**Docker & Gunicorn**

*A aplicação roda em produção utilizando Gunicorn como servidor WSGI atrás de um container Docker. Isso garante que a aplicação reinicie automaticamente, gerencie múltiplos workers para requisições simultâneas e isole o ambiente de execução do sistema operacional da VM.*

**Front-end**

*O front-end foi construído com HTML5, CSS3 e Vanilla JS, sem frameworks pesados pois não julguei necessário. O intuito era construir uma tela apenas para obter uma auditoria humana para evitar spam excessivo. Utilizamos o conceito de Glassmorphism e um tema Dark Mode*

## Features

As principais funcionalidades desenhadas para agilidade na tomada de decisão:

1. **Monitoramento e Classificação em Tempo Real:**
   Identifica automaticamente o tipo de falha. Se for `LOS` (Rompimento), exibe badge vermelha. Se for `POWER` (Energia), exibe badge laranja.

   ![Dashboard Monitor](./images/dashboard.png)

2. **Detalhes e Enriquecimento de Dados:**
   Ao clicar em um incidente, o sistema cruza o SN da ONU com o Sistema de gerenciamento de OLT para buscar o nome e telefone do cliente, exibindo também o status atual da conexão.

   ![Modal Detalhes](./images/details.png)

3. **Flap Damping (Controle de Oscilação):**
   Lógica inteligente que impede envios duplicados. Se um disparo foi realizado para uma porta/OLT específica, o sistema bloqueia novos alertas dessa mesma origem por 24 horas, evitando spam para o cliente final e envio somente 1 vez ao dia.

4. **Automação de Token:**
   O backend possui um wrapper `safe_api_get` que detecta erros 401 (Unauthorized), realiza o login automaticamente e refaz a requisição original sem intervenção humana.

## Instruções de execução

Pré-requisitos: Ter o **Docker** e **Docker Compose** instalados na máquina.

1. **Clone o repositório:**
```bash
   git clone [https://github.com/ederdsc/disparo_hsm_cn.git](https://github.com/ederdsc/disparo_hsm_cn.git)
   cd disparo_hsm
```

2. **Configure as Variáveis de Ambiente: Crie um arquivo .env na raiz do projeto com suas credenciais:**

Snippet de código
# API SISTEMA DE GERENCIAMENTO DE OLT
API_BASE_URL=https://api.seuisp.com.br
API_AUTH_URL=https://api.seuisp.com.br/oauth/login
API_USER=seu_usuario
API_PASS=sua_senha

# API HSM
URL_HSM=https://api.hsm.com/send
TOKEN_HSM=seu_token

**Execute com Docker Compose:**
```bash
docker compose up -d --build
```