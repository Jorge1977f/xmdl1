"""Conteúdo de ajuda detalhado da aplicação."""
from __future__ import annotations

from html import escape

# Aviso de primeiro uso - será exibido em destaque
FIRST_USE_WARNING = """
<div style="background: #fff3cd; border: 3px solid #ff6b6b; border-radius: 10px; padding: 20px; margin-bottom: 20px; text-align: center;">
    <h2 style="color: #c92a2a; margin-top: 0;">⚠️ LEIA COM ATENÇÃO - SEQUÊNCIA RECOMENDADA</h2>
    <p style="font-size: 16px; color: #333; line-height: 1.6;">
        <b>Bem-vindo ao XML Downloader!</b><br><br>
        Este programa foi desenvolvido para automatizar o download de documentos fiscais (NFS-e) 
        de forma inteligente e segura. Antes de começar a usar, siga os passos abaixo:<br><br>
        <b style="color: #c92a2a;">1. Cadastre uma licença</b> (Módulo: Licenças - temporária de 7 dias ou adquira)<br>
        <b style="color: #c92a2a;">2. Cadastre sua empresa</b> (Módulo: Empresas)<br>
        <b style="color: #c92a2a;">3. Configure o certificado digital</b> (Módulo: Configurações)<br>
        <b style="color: #c92a2a;">4. Configure o acesso ao portal</b> (Módulo: Configurações)<br>
        <b style="color: #c92a2a;">5. Realize o primeiro download</b> (Módulo: Download)<br>
        <b style="color: #c92a2a;">6. Revise os documentos importados</b> (Módulo: XMLs)<br>
        <b style="color: #c92a2a;">7. Gere relatórios conforme necessário</b> (Módulo: Relatórios)<br><br>
        <i>Pressione F1 em qualquer tela para obter ajuda contextual detalhada.</i>
    </p>
</div>
"""

TOPIC_TITLES = {
    "geral": "Manual Geral",
    "dashboard": "Ajuda - Dashboard",
    "empresas": "Ajuda - Empresas",
    "download": "Ajuda - Download",
    "xmls": "Ajuda - XMLs",
    "manifestacao": "Ajuda - Manifestação",
    "logs": "Ajuda - Logs",
    "relatorios": "Ajuda - Relatórios",
    "configuracoes": "Ajuda - Configurações",
    "licencas": "Ajuda - Licenças",
    "limpeza_backup": "Ajuda - Limpeza e Backup",
    "ajuda": "Manual Geral",
}

TOPIC_HTML = {
    "geral": f"""
    {FIRST_USE_WARNING}
    <h1>Manual Geral do XML Downloader</h1>
    <p>Este programa foi desenvolvido para simplificar e automatizar o processo de download de documentos fiscais (NFS-e) 
    de forma inteligente, segura e rastreável. O sistema integra múltiplas funcionalidades em um único ambiente.</p>
    
    <h2>O que é XML Downloader?</h2>
    <p>XML Downloader é um software especializado que:</p>
    <ul>
      <li>Conecta-se automaticamente aos portais de NFS-e das prefeituras</li>
      <li>Baixa documentos fiscais (NFS-e tomada e prestada) de forma segura</li>
      <li>Importa e organiza os XMLs em banco de dados local</li>
      <li>Gera relatórios analíticos e exporta em PDF/Excel</li>
      <li>Mantém histórico completo de todas as operações</li>
      <li>Oferece limpeza e backup automático dos dados</li>
    </ul>
    
    <h2>Fluxo Recomendado de Uso (Primeiras Vezes)</h2>
    <div style="text-align: center; margin: 20px 0;">
        <img src="app/resources/help_images/img_fluxo_geral.png" width="400" alt="Fluxo Geral de Uso" style="border: 1px solid #ddd; border-radius: 8px;">
    </div>
    <ol>
      <li><b>Licenças</b>: Cadastre uma licença (temporária de 7 dias ou adquira uma)</li>
      <li><b>Empresas</b>: Cadastre os dados básicos da empresa (Razão Social, CNPJ, UF)</li>
      <li><b>Configurações</b>: Configure o certificado digital e acesso ao portal</li>
      <li><b>Download</b>: Execute o primeiro download de documentos</li>
      <li><b>XMLs</b>: Revise os documentos importados, abra PDFs, exclua se necessário</li>
      <li><b>Relatórios</b>: Gere relatórios analíticos e exporte em PDF ou Excel</li>
      <li><b>Logs</b>: Consulte quando houver dúvidas sobre o que aconteceu</li>
    </ol>
    
    <h2>Fluxo de Uso Contínuo (Operacional)</h2>
    <ol>
      <li>Acesse o <b>Dashboard</b> para visão geral do sistema</li>
      <li>Selecione a empresa desejada no topo da janela</li>
      <li>Acesse o módulo <b>Download</b> para buscar novos documentos</li>
      <li>Revise em <b>XMLs</b> se necessário</li>
      <li>Exporte relatórios em <b>Relatórios</b></li>
    </ol>
    
    <h2>Módulos Disponíveis</h2>
    <ul>
      <li><b>Dashboard</b>: Visão rápida do status geral e estatísticas</li>
      <li><b>Empresas</b>: Cadastro e gerenciamento de empresas</li>
      <li><b>Configurações</b>: Certificado digital, portal, parâmetros do sistema</li>
      <li><b>Download</b>: Busca e importação de documentos do portal</li>
      <li><b>XMLs</b>: Conferência operacional de documentos importados</li>
      <li><b>Manifestação</b>: Acompanhamento de filas de manifestação (NF-e)</li>
      <li><b>Relatórios</b>: Análise e exportação de dados em PDF/Excel</li>
      <li><b>Limpeza e Backup</b>: Limpeza de arquivos e backup de dados</li>
      <li><b>Logs</b>: Histórico técnico de todas as operações</li>
      <li><b>Licenças</b>: Gerenciamento de licenças e ativação</li>
    </ul>
    
    <h2>Atalhos de Teclado</h2>
    <ul>
      <li><b>F1</b>: Abre a ajuda detalhada da tela atual em qualquer módulo</li>
    </ul>
    
    <h2>Dicas Práticas Essenciais</h2>
    <ul>
      <li><b>Primeira execução</b>: Configure o certificado ANTES de tentar baixar qualquer documento</li>
      <li><b>Navegador oculto</b>: Quando ativado nas configurações, o sistema abre o navegador automaticamente para seleção de certificado</li>
      <li><b>Período de busca</b>: Use períodos menores (30 dias) para primeira busca, depois amplie conforme necessário</li>
      <li><b>Pasta de downloads</b>: Mantenha a pasta de downloads limpa e acessível</li>
      <li><b>Relatórios</b>: Os relatórios mostram dados desagrupados (uma linha por documento) para facilitar exportação</li>
      <li><b>Conferência</b>: Use a tela de XMLs para conferência operacional e Relatórios para exportação</li>
      <li><b>Backup regular</b>: Faça backup regularmente usando a tela de Limpeza e Backup</li>
    </ul>
    
    <h2>Problemas Comuns e Soluções</h2>
    <ul>
      <li><b>Portal não conectou</b>: Verifique certificado, senha e tempo de espera nas configurações</li>
      <li><b>Nenhum documento foi importado</b>: Abra a pasta de downloads e confirme se os arquivos foram salvos</li>
      <li><b>Busca não encontrou resultados</b>: Tente diferentes critérios: nome, CNPJ, número, chave ou valor</li>
      <li><b>Erro ao abrir PDF</b>: Verifique se o arquivo XML foi processado corretamente</li>
      <li><b>Licença expirada</b>: Acesse o módulo de Licenças para renovar</li>
    </ul>
    
    <h2>Suporte e Ajuda</h2>
    <ul>
      <li>Pressione <b>F1</b> em qualquer tela para ajuda contextual</li>
      <li>Acesse o módulo <b>Logs</b> para entender o que aconteceu em caso de erro</li>
      <li>Consulte o manual completo no módulo <b>Ajuda</b></li>
    </ul>
    """,
    
    "dashboard": """
    <h1>Dashboard - Visão Geral do Sistema</h1>
    <p>O Dashboard é a tela inicial que oferece uma visão rápida e consolidada do estado geral do sistema e da empresa ativa.</p>
    
    <h2>O que você vê no Dashboard?</h2>
    <ul>
      <li><b>Empresa Ativa</b>: Mostra qual empresa está selecionada no momento (canto superior direito)</li>
      <li><b>Estatísticas Gerais</b>: Quantidade total de empresas cadastradas e documentos importados</li>
      <li><b>Taxa de Sucesso</b>: Percentual de documentos processados com sucesso</li>
      <li><b>Informações de Banco de Dados</b>: Status da conexão com o banco de dados local</li>
      <li><b>Documentos Recentes</b>: Lista dos 20 documentos mais recentemente importados</li>
    </ul>
    
    <h2>Como Usar o Dashboard</h2>
    <ol>
      <li>Verifique qual empresa está selecionada no topo da janela</li>
      <li>Observe as estatísticas para ter uma visão geral</li>
      <li>Consulte os documentos recentes para confirmar que as importações estão funcionando</li>
      <li>Use o Dashboard como ponto de entrada, mas realize as operações específicas nos módulos dedicados</li>
    </ol>
    
    <h2>Dicas</h2>
    <ul>
      <li>O Dashboard é apenas informativo; para realizar ações, use os módulos específicos</li>
      <li>Se nenhum documento aparecer, verifique se você já executou um download no módulo Download</li>
      <li>A empresa selecionada no topo afeta todos os outros módulos</li>
    </ul>
    """,
    
    "empresas": """
    <h1>Empresas - Cadastro e Gerenciamento</h1>
    <p>Neste módulo você cadastra, edita, consulta e exclui as empresas que utilizarão o sistema. 
    Cada empresa tem seus próprios documentos, configurações de certificado e acesso ao portal.</p>
    
    <h2>Campos Obrigatórios para Cadastro</h2>
    <ul>
      <li><b>Razão Social</b>: Nome completo da empresa (obrigatório)</li>
      <li><b>CNPJ</b>: Número do CNPJ (obrigatório, sem máscara)</li>
      <li><b>UF</b>: Estado onde a empresa está sediada (obrigatório)</li>
    </ul>
    
    <h2>Campos Opcionais</h2>
    <ul>
      <li>Nome Fantasia</li>
      <li>Endereço</li>
      <li>Telefone</li>
      <li>E-mail</li>
      <li>Responsável</li>
      <li>Observações</li>
    </ul>
    
    <h2>Como Cadastrar uma Nova Empresa (com Consulta Online)</h2>
    <p>Para facilitar o cadastro, o sistema permite consultar os dados da empresa diretamente na Receita Federal:</p>
    
    <div style="text-align: center; margin: 15px 0;">
        <img src="app/resources/help_images/img_cnpj.png" width="500" alt="Fluxo de Consulta CNPJ" style="border: 1px solid #ddd; border-radius: 8px;">
    </div>
    
    <ol>
      <li>Clique no botão <b>"Nova Empresa"</b> no topo da tela</li>
      <li><b>Passo 1:</b> Digite apenas o número do <b>CNPJ</b> no campo correspondente</li>
      <li><b>Passo 2:</b> Clique no botão <b>"Consultar CNPJ"</b> (ícone de lupa) ao lado do campo</li>
      <li><b>Passo 3:</b> Aguarde o sistema carregar os dados da Receita Federal</li>
      <li>Verifique se os campos (Razão Social, Endereço, etc.) foram preenchidos corretamente</li>
      <li>Selecione a <b>UF</b> (Estado) caso não tenha sido preenchida automaticamente</li>
      <li>Clique em <b>"Salvar"</b> para confirmar o cadastro</li>
    </ol>
    
    <h2>Como Editar uma Empresa</h2>
    <ol>
      <li>Selecione a empresa na lista</li>
      <li>Clique no botão <b>"Editar"</b></li>
      <li>Modifique os dados conforme necessário</li>
      <li>Clique em <b>"Salvar"</b> para confirmar as alterações</li>
    </ol>
    
    <h2>Como Excluir uma Empresa</h2>
    <ol>
      <li>Selecione a empresa na lista</li>
      <li>Clique no botão <b>"Excluir"</b></li>
      <li>Confirme a exclusão na caixa de diálogo</li>
      <li><b>ATENÇÃO:</b> A exclusão remove todos os dados associados à empresa (documentos, configurações, etc.)</li>
    </ol>
    
    <h2>Recursos Especiais de Importação</h2>
    
    <h3>Importar Dados do PDF do CNPJ</h3>
    <ol>
      <li>Clique em <b>"Importar PDF do CNPJ"</b></li>
      <li>Selecione um arquivo PDF do comprovante de inscrição do CNPJ já salvo no seu computador</li>
      <li>O sistema lerá automaticamente os dados do PDF e preencherá os campos</li>
      <li>Revise os dados e clique em <b>"Salvar"</b></li>
    </ol>
    
    <h3>Consultar CNPJ Online</h3>
    <ol>
      <li>Clique em <b>"Consultar CNPJ Online"</b></li>
      <li>Digite o CNPJ (com ou sem máscara)</li>
      <li>O sistema consultará a base de dados pública e preencherá os dados automaticamente</li>
      <li>Revise os dados e clique em <b>"Salvar"</b></li>
    </ol>
    
    <h2>Dicas Importantes</h2>
    <ul>
      <li>O CNPJ é único: o sistema impede o cadastro de duas empresas com o mesmo CNPJ</li>
      <li>Digite o CNPJ com ou sem máscara; o sistema salva apenas os números</li>
      <li>A Razão Social deve ser exatamente como consta na Junta Comercial</li>
      <li>Você pode ter múltiplas empresas cadastradas e alternar entre elas</li>
      <li>Cada empresa terá suas próprias configurações de certificado e portal</li>
    </ul>
    
    <h2>Próximos Passos</h2>
    <p>Após cadastrar a empresa, acesse o módulo <b>Configurações</b> para configurar o certificado digital e o acesso ao portal.</p>
    """,
    
    "download": """
    <h1>Download - Busca e Importação de Documentos</h1>
    <p>Este é o módulo principal para buscar e importar documentos fiscais (NFS-e) do portal da prefeitura. 
    Aqui você controla todo o processo de download, desde a seleção de período até a importação no banco de dados.</p>
    
    <h2>Elementos da Tela</h2>
    
    <h3>Seleção de Empresa</h3>
    <p>No topo, selecione qual empresa deseja buscar documentos. A empresa selecionada determinará 
    qual certificado e credenciais serão usados para conectar ao portal.</p>
    
    <h3>Tipo de Documento</h3>
    <ul>
      <li><b>NFS-e Tomada</b>: Documentos que sua empresa recebeu (serviços prestados por terceiros)</li>
      <li><b>NFS-e Prestada</b>: Documentos que sua empresa emitiu (serviços prestados pela empresa)</li>
    </ul>
    
    <h3>Período de Busca</h3>
    <ul>
      <li><b>Data Inicial</b>: Primeiro dia do período que deseja buscar</li>
      <li><b>Data Final</b>: Último dia do período que deseja buscar</li>
      <li><b>Dica</b>: Para primeira busca, use períodos menores (30 dias) para testar o fluxo</li>
    </ul>
    
    <h3>NSU (Número Sequencial Único)</h3>
    <p>Campo avançado para buscar a partir de um NSU específico. Deixe em branco para buscar desde o início.</p>
    
    <h2>Métodos de Download: API vs Portal</h2>
    <div style="text-align: center; margin: 15px 0;">
        <img src="app/resources/help_images/img_download_api.png" width="600" alt="Métodos de Download" style="border: 1px solid #ddd; border-radius: 8px;">
    </div>
    
    <h3>1. Baixar via API (Recomendado e Mais Rápido)</h3>
    <p>Este é o método mais eficiente e rápido para baixar documentos.</p>
    <ol>
      <li>Selecione a <b>empresa</b> e o <b>tipo de documento</b></li>
      <li>No campo <b>NSU Inicial</b>, se você não souber qual é, <b>pode colocar 1</b></li>
      <li>No campo <b>NSU Final</b>, coloque um <b>valor bem alto</b> (ex: 999999) para que ele procure de forma rápida todos os documentos</li>
      <li>Clique em <b>"Baixar via API"</b></li>
    </ol>
    
    <h3>2. Baixar via Portal (Mais Demorado)</h3>
    <p>Use este método como alternativa. <b>Importante:</b> O certificado digital precisa estar instalado no computador (no Windows).</p>
    <ol>
      <li>Selecione a <b>empresa</b> e o <b>tipo de documento</b></li>
      <li>Informe o <b>período</b> (Data Inicial e Final)</li>
      <li>Clique em <b>"Baixar via Portal"</b></li>
      <li>A única coisa que você precisará fazer é <b>selecionar o certificado</b> na janela que aparecer, o resto o sistema faz sozinho</li>
      <li><i>Nota: Este processo é mais demorado que a API, pois simula a navegação humana.</i></li>
    </ol>
    
    <h2>Entendendo o Processo de Download</h2>
    
    <h3>Etapas do Download</h3>
    <ol>
      <li><b>Conexão ao Portal</b>: O sistema conecta usando o certificado configurado</li>
      <li><b>Busca de Documentos</b>: Procura por documentos no período especificado</li>
      <li><b>Download de Arquivos</b>: Baixa os XMLs para a pasta configurada</li>
      <li><b>Importação no Banco</b>: Importa os XMLs para o banco de dados local</li>
      <li><b>Processamento</b>: Processa e indexa os documentos para busca rápida</li>
    </ol>
    
    <h3>Indicadores de Status</h3>
    <ul>
      <li><b>Barra de Progresso</b>: Mostra o percentual de conclusão (0-100%)</li>
      <li><b>Caixas de Status</b>: Mostram em qual etapa o sistema está no momento</li>
      <li><b>Grade de Resultados</b>: Resumo do job executado (documentos baixados, importados, erros)</li>
    </ul>
    
    <h2>Navegador Oculto (Headless)</h2>
    <p>Quando ativado nas Configurações, o sistema tenta automatizar o máximo possível:</p>
    <ul>
      <li>Abre o navegador automaticamente para seleção de certificado</li>
      <li>Continua o processo com mínima intervenção do usuário</li>
      <li>Recomendado após o fluxo visível estar funcionando corretamente</li>
    </ul>
    
    <h2>Cancelar um Download</h2>
    <ol>
      <li>Clique no botão <b>"Cancelar"</b> durante a execução</li>
      <li>O sistema preservará tudo que já foi baixado e importado até o momento seguro</li>
      <li>Você pode retomar a busca depois sem perder dados</li>
    </ol>
    
    <h2>Ações Adicionais</h2>
    <ul>
      <li><b>Abrir Pasta</b>: Abre a pasta de downloads para visualizar os arquivos</li>
      <li><b>Visualizar XML</b>: Abre o XML selecionado na grade de resultados</li>
    </ul>
    
    <h2>Dicas Importantes</h2>
    <ul>
      <li>Certifique-se de que o certificado está configurado ANTES de fazer o primeiro download</li>
      <li>Se o portal não conectar, verifique a senha nas Configurações</li>
      <li>Use períodos menores para primeira busca (máximo 30 dias)</li>
      <li>Se houver muitos documentos, o download pode levar alguns minutos</li>
      <li>Não feche o programa durante o download</li>
      <li>Consulte os Logs se houver erros durante o processo</li>
    </ul>
    """,
    
    "xmls": """
    <h1>XMLs - Conferência Operacional de Documentos</h1>
    <p>Este módulo é destinado à conferência operacional dos documentos já importados. 
    Aqui você visualiza, busca, abre PDFs/XMLs e exclui documentos conforme necessário.</p>
    
    <h2>Elementos da Tela</h2>
    
    <h3>Seleção de Empresa</h3>
    <p>Selecione a empresa cujos documentos deseja revisar. Apenas os documentos dessa empresa serão exibidos.</p>
    
    <h3>Filtros Disponíveis</h3>
    <ul>
      <li><b>Período</b>: Filtra documentos por data de emissão</li>
      <li><b>Status</b>: Filtra por status do documento (Ativo, Cancelado, etc.)</li>
      <li><b>Tipo</b>: Filtra por tipo (Tomada ou Prestada)</li>
      <li><b>Busca Inteligente</b>: Busca por chave, número, emitente, destinatário ou CNPJ</li>
    </ul>
    
    <h2>Exportação e Visualização em PDF</h2>
    <div style="text-align: center; margin: 15px 0;">
        <img src="app/resources/help_images/img_xml.png" width="600" alt="Visualizar PDF e Exportar" style="border: 1px solid #ddd; border-radius: 8px;">
    </div>
    
    <h3>Como Exportar XMLs</h3>
    <p>O sistema permite exportar todos os arquivos XML de um determinado período de uma só vez:</p>
    <ol>
      <li>Selecione a empresa e o tipo de documento</li>
      <li>Selecione o <b>período desejado</b> (Data Inicial e Final)</li>
      <li>Clique no botão <b>"Exportar XMLs"</b></li>
      <li>O sistema irá exportar todos os arquivos do período selecionado para a pasta escolhida</li>
    </ol>

    <h3>Como Visualizar o PDF do Documento</h3>
    <p>Para ver o documento formatado (DANFE/Formulário):</p>
    <ol>
      <li>Encontre o documento desejado na lista</li>
      <li>Dê um <b>Duplo Clique</b> na linha do documento</li>
      <li>O sistema irá abrir automaticamente o arquivo PDF com o formulário completo da nota</li>
    </ol>

    <h2>Como Usar os Filtros</h2>
    <ol>
      <li>Selecione a empresa desejada</li>
      <li>Use os filtros de período, status e tipo conforme necessário</li>
      <li>Na busca inteligente, digite o que procura (chave, número, nome, CNPJ)</li>
      <li>A grade se atualiza automaticamente com os resultados</li>
    </ol>
    
    <h2>Colunas da Grade</h2>
    <ul>
      <li><b>Chave</b>: Chave de acesso do documento (44 dígitos)</li>
      <li><b>Número</b>: Número do documento</li>
      <li><b>Emitente</b>: Razão social de quem emitiu</li>
      <li><b>CNPJ Emitente</b>: CNPJ de quem emitiu</li>
      <li><b>Destinatário</b>: Razão social de quem recebeu</li>
      <li><b>CNPJ Destinatário</b>: CNPJ de quem recebeu</li>
      <li><b>Data</b>: Data de emissão do documento</li>
      <li><b>Valor</b>: Valor total do documento</li>
      <li><b>Status</b>: Status atual do documento</li>
    </ul>
    
    <h2>Ações Disponíveis</h2>
    
    <h3>Abrir XML</h3>
    <ol>
      <li>Selecione o documento na grade</li>
      <li>Clique em <b>"Abrir XML"</b></li>
      <li>O arquivo XML será aberto em seu editor padrão</li>
    </ol>
    
    <h3>Abrir PDF (DANFE/DANFSE)</h3>
    <ol>
      <li>Selecione o documento na grade</li>
      <li>Clique em <b>"Abrir PDF"</b></li>
      <li>O PDF será aberto em seu leitor padrão</li>
    </ol>
    
    <h3>Excluir XML</h3>
    <ol>
      <li>Selecione o documento na grade</li>
      <li>Clique em <b>"Excluir XML"</b></li>
      <li>Confirme a exclusão na caixa de diálogo</li>
      <li>O documento será removido do banco de dados E da pasta de downloads</li>
      <li><b>ATENÇÃO:</b> Esta ação é irreversível</li>
    </ol>
    
    <h2>Sincronizar Pasta</h2>
    <p>Esta função relê a pasta de downloads e importa qualquer arquivo novo que não esteja no banco:</p>
    <ol>
      <li>Clique em <b>"Sincronizar Pasta"</b></li>
      <li>O sistema verificará a pasta configurada</li>
      <li>Qualquer XML novo será importado automaticamente</li>
      <li>Útil se você adicionou arquivos manualmente à pasta</li>
    </ol>
    
    <h2>Dicas Importantes</h2>
    <ul>
      <li>Use esta tela para conferência operacional dia a dia</li>
      <li>Para análise e exportação, use o módulo <b>Relatórios</b></li>
      <li>A busca inteligente funciona com ou sem máscara (ex: "123.456.789-00" ou "12345678900")</li>
      <li>Você pode excluir documentos duplicados ou incorretos aqui</li>
      <li>A exclusão remove tanto do banco quanto da pasta</li>
    </ul>
    
    <h2>Próximos Passos</h2>
    <p>Após revisar os documentos, acesse o módulo <b>Relatórios</b> para gerar análises e exportar em PDF ou Excel.</p>
    """,
    
    "manifestacao": """
    <h1>Manifestação - Acompanhamento de Filas (NF-e)</h1>
    <p>Este módulo é destinado ao acompanhamento de filas e eventos ligados à manifestação de documentos NF-e. 
    Ele é especialmente útil para empresas que precisam manifestar recebimento ou outras ações sobre notas fiscais eletrônicas.</p>
    
    <h2>O que é Manifestação?</h2>
    <p>Manifestação é um processo onde a empresa que recebeu uma NF-e (Nota Fiscal Eletrônica) 
    comunica à Receita Federal sua posição sobre o documento (recebimento, desconhecimento, etc.).</p>
    
    <h2>Elementos da Tela</h2>
    
    <h3>Seleção de Empresa</h3>
    <p>Selecione a empresa para visualizar sua fila de manifestação.</p>
    
    <h3>Botão Carregar</h3>
    <p>Clique para atualizar a fila de manifestação da empresa selecionada.</p>
    
    <h2>Colunas da Grade</h2>
    <ul>
      <li><b>Chave</b>: Chave de acesso da NF-e</li>
      <li><b>Status</b>: Status atual da manifestação</li>
      <li><b>Tentativas</b>: Número de tentativas de manifestação</li>
      <li><b>Próxima Tentativa</b>: Data e hora da próxima tentativa automática</li>
      <li><b>Última Resposta</b>: Resposta da última tentativa</li>
    </ul>
    
    <h2>Ações Disponíveis</h2>
    
    <h3>Manifestar</h3>
    <p>Envia a manifestação para a Receita Federal. Disponível quando há documentos na fila.</p>
    
    <h3>Reprocessar</h3>
    <p>Retenta o processamento de manifestações que falharam anteriormente.</p>
    
    <h2>Dicas Importantes</h2>
    <ul>
      <li>Se sua empresa não usa manifestação com frequência, você pode deixar esta tela apenas para conferência eventual</li>
      <li>O sistema tenta reprocessar automaticamente em intervalos regulares</li>
      <li>Consulte os Logs se houver erros no processo de manifestação</li>
      <li>Manifestação é obrigatória em alguns casos; verifique a legislação vigente</li>
    </ul>
    """,
    
    "logs": """
    <h1>Logs - Histórico Técnico de Operações</h1>
    <p>Este módulo mostra os registros técnicos de tudo que aconteceu no sistema. 
    Use-o para entender erros, rastrear operações e obter informações para suporte técnico.</p>
    
    <h2>O que são Logs?</h2>
    <p>Logs são registros detalhados de cada operação realizada pelo sistema, incluindo:</p>
    <ul>
      <li>Conexões ao portal</li>
      <li>Downloads de documentos</li>
      <li>Importações no banco de dados</li>
      <li>Erros e exceções</li>
      <li>Avisos e informações gerais</li>
    </ul>
    
    <h2>Como Usar os Logs</h2>
    <ol>
      <li>Selecione um arquivo de log na lista à esquerda</li>
      <li>O conteúdo do arquivo será exibido no painel à direita</li>
      <li>Use a barra de rolagem para navegar pelo arquivo</li>
      <li>Procure por mensagens sobre o que você está investigando</li>
    </ol>
    
    <h2>Tipos de Mensagens nos Logs</h2>
    <ul>
      <li><b>INFO</b>: Informações gerais sobre operações normais</li>
      <li><b>WARNING</b>: Avisos sobre situações que podem precisar atenção</li>
      <li><b>ERROR</b>: Erros que impediram uma operação de completar</li>
      <li><b>DEBUG</b>: Informações detalhadas para diagnóstico técnico</li>
    </ul>
    
    <h2>Mensagens Comuns e o que Significam</h2>
    
    <h3>Relacionadas ao Portal</h3>
    <ul>
      <li><b>"Portal connection established"</b>: Conexão bem-sucedida ao portal</li>
      <li><b>"Portal connection failed"</b>: Falha na conexão; verifique certificado e senha</li>
      <li><b>"Certificate error"</b>: Problema com o certificado digital</li>
    </ul>
    
    <h3>Relacionadas ao Download</h3>
    <ul>
      <li><b>"Starting download"</b>: Início do processo de download</li>
      <li><b>"Downloaded X documents"</b>: Quantidade de documentos baixados</li>
      <li><b>"Download failed"</b>: Falha no download; verifique a pasta de downloads</li>
    </ul>
    
    <h3>Relacionadas à Importação</h3>
    <ul>
      <li><b>"Importing documents"</b>: Início da importação no banco de dados</li>
      <li><b>"Imported X documents"</b>: Quantidade de documentos importados com sucesso</li>
      <li><b>"Import error"</b>: Erro durante a importação; verifique o arquivo XML</li>
    </ul>
    
    <h2>Ações Disponíveis</h2>
    
    <h3>Atualizar</h3>
    <p>Recarrega o arquivo de log para ver as mensagens mais recentes.</p>
    
    <h3>Limpar</h3>
    <p>Limpa o arquivo de log selecionado. Use com cuidado, pois não pode ser desfeito.</p>
    
    <h2>Dicas para Diagnóstico</h2>
    <ul>
      <li>Quando um job falhar, abra os Logs e procure por mensagens de ERROR</li>
      <li>Leia a mensagem de erro completa para entender o problema</li>
      <li>Se for pedir suporte, copie a mensagem de erro mais completa que aparecer aqui</li>
      <li>Procure por mensagens sobre portal, certificado, download, importação e pasta monitorada</li>
      <li>Use Ctrl+F (ou Cmd+F no Mac) para buscar palavras-chave no arquivo</li>
    </ul>
    """,
    
    "relatorios": """
    <h1>Relatórios - Análise e Exportação de Dados</h1>
    <p>Este módulo oferece análise avançada dos documentos importados e permite exportação em PDF ou Excel. 
    Diferentemente da tela de XMLs (conferência operacional), aqui os dados são apresentados de forma analítica e pronta para exportação.</p>
    
    <h2>Elementos da Tela</h2>
    
    <h3>Filtros Principais</h3>
    <ul>
      <li><b>Empresa</b>: Selecione a empresa cujos dados deseja analisar</li>
      <li><b>Tipo de Documento</b>: Escolha entre Tomada ou Prestada</li>
      <li><b>Data Inicial e Final</b>: Período de análise</li>
    </ul>
    
    <h3>Busca Inteligente</h3>
    <p>Busque por <b>nome</b>, <b>CNPJ</b>, <b>número</b>, <b>chave</b> ou <b>valor</b> para filtrar ainda mais os resultados.</p>
    
    <h2>Visualização Rápida de Documentos (PDF)</h2>
    <div style="text-align: center; margin: 15px 0;">
        <img src="app/resources/help_images/img_relatorios.png" width="500" alt="Abrir PDF no Relatório" style="border: 1px solid #ddd; border-radius: 8px;">
    </div>
    <p>Para facilitar a conferência de dados diretamente da tela de relatórios, o sistema permite abrir o formulário PDF da nota com apenas um duplo clique.</p>
    <ul>
      <li>Disponível nas listas de: <b>Clientes</b>, <b>Fornecedores</b> e <b>Serviços</b></li>
      <li>Basta dar um <b>duplo clique</b> na linha desejada</li>
      <li>O sistema abrirá automaticamente o documento formatado em PDF para conferência</li>
    </ul>
    
    <h2>Abas de Relatórios Disponíveis</h2>
    
    <h3>Financeiro</h3>
    <ul>
      <li>Mostra resumo financeiro dos documentos</li>
      <li>Inclui totalizações por período</li>
      <li>Útil para reconciliação contábil</li>
    </ul>
    
    <h3>Clientes</h3>
    <ul>
      <li>Análise de documentos por cliente (para NFS-e Prestada)</li>
      <li>Mostra valor total por cliente</li>
      <li>Útil para análise de receita por cliente</li>
    </ul>
    
    <h3>Fornecedores</h3>
    <ul>
      <li>Análise de documentos por fornecedor (para NFS-e Tomada)</li>
      <li>Mostra valor total por fornecedor</li>
      <li>Útil para análise de despesa por fornecedor</li>
    </ul>
    
    <h3>Serviços</h3>
    <ul>
      <li>Análise por tipo de serviço prestado/recebido</li>
      <li>Mostra quantidade e valor por serviço</li>
      <li>Útil para análise de mix de serviços</li>
    </ul>
    
    <h3>Impostos</h3>
    <ul>
      <li>Resumo de impostos retidos e devidos</li>
      <li>Mostra ISS, INSS e outros impostos</li>
      <li>Útil para planejamento fiscal</li>
    </ul>
    
    <h3>Tendências</h3>
    <ul>
      <li>Análise de tendências ao longo do tempo</li>
      <li>Mostra evolução de receitas/despesas</li>
      <li>Útil para análise de desempenho</li>
    </ul>
    
    <h3>Cancelamentos</h3>
    <ul>
      <li>Mostra documentos cancelados no período</li>
      <li>Inclui motivo do cancelamento</li>
      <li>Útil para auditoria e compliance</li>
    </ul>
    
    <h2>Como Usar os Relatórios</h2>
    <ol>
      <li>Selecione a empresa desejada</li>
      <li>Escolha o tipo de documento (Tomada ou Prestada)</li>
      <li>Informe o período (data inicial e final)</li>
      <li>Use a busca inteligente se precisar filtrar ainda mais</li>
      <li>Clique na aba do relatório desejado</li>
      <li>Os dados serão exibidos em uma grade desagrupada (uma linha por documento)</li>
    </ol>
    
    <h2>Exportação de Dados</h2>
    
    <h3>Exportar para PDF</h3>
    <ol>
      <li>Configure os filtros conforme desejado</li>
      <li>Clique em <b>"Exportar PDF"</b></li>
      <li>Escolha o local para salvar o arquivo</li>
      <li>O PDF será gerado com cabeçalho da empresa, período e totalizações</li>
    </ol>
    
    <h3>Exportar para Excel</h3>
    <ol>
      <li>Configure os filtros conforme desejado</li>
      <li>Clique em <b>"Exportar Excel"</b></li>
      <li>Escolha o local para salvar o arquivo</li>
      <li>A planilha será gerada com cabeçalho, dados desagrupados e totalizações</li>
    </ol>
    
    <h2>Ações Adicionais</h2>
    <ul>
      <li><b>Abrir DANFE/XML</b>: Abre o documento selecionado na grade</li>
      <li><b>Drill-Down</b>: Clique em um item para expandir e ver detalhes</li>
    </ul>
    
    <h2>Formato dos Dados</h2>
    <p>Os resultados aparecem <b>desagrupados</b>, ou seja, cada documento fica em sua própria linha. 
    Isso facilita a conferência, exportação e integração com outros sistemas.</p>
    
    <h2>Dicas Importantes</h2>
    <ul>
      <li>Use períodos menores (máximo 3 meses) para relatórios mais rápidos</li>
      <li>A busca inteligente funciona com ou sem máscara</li>
      <li>Os totalizadores aparecem no final de cada relatório</li>
      <li>Exporte regularmente para manter backup dos dados</li>
      <li>Use Excel para análises adicionais e gráficos personalizados</li>
    </ul>
    """,
    
    "configuracoes": """
    <h1>Configurações - Certificado, Portal e Parâmetros</h1>
    
    <div style="background: #e8f5e9; border-left: 4px solid #4caf50; padding: 15px; margin-bottom: 20px;">
        <h3 style="color: #2e7d32; margin-top: 0;">💡 IMPORTANTE: O que preencher nesta versão</h3>
        <p style="font-size: 14px; margin-bottom: 0;">
            Nesta versão do sistema, <b>você só precisa preencher o Certificado Digital e a Senha</b>. 
            Todas as outras configurações (Portal, Pastas, etc.) são <b>opcionais</b> e o sistema 
            funcionará perfeitamente com os valores padrão.
        </p>
    </div>
    
    <p>Este módulo centraliza todas as configurações necessárias para o funcionamento do sistema: 
    certificado digital, acesso ao portal, pasta de downloads e parâmetros gerais.</p>
    
    <h2>Abas de Configuração</h2>
    
    <h2>ABA: CERTIFICADO</h2>
    
    <h3>O que é o Certificado Digital?</h3>
    <p>O certificado digital é um arquivo que comprova a identidade da empresa perante a Receita Federal 
    e é obrigatório para acessar o portal de NFS-e.</p>
    
    <h3>Como Configurar o Certificado</h3>
    <ol>
      <li>Clique em <b>"Procurar"</b> para selecionar o arquivo do certificado</li>
      <li>Selecione o arquivo .pfx ou .p12 do seu certificado</li>
      <li>Digite a <b>Senha do Certificado</b> (fornecida quando você adquiriu o certificado)</li>
      <li>Clique em <b>"Salvar Certificado"</b></li>
      <li>Uma mensagem de sucesso indicará que o certificado foi salvo</li>
    </ol>
    
    <h3>Dicas sobre Certificado</h3>
    <ul>
      <li>O certificado é específico de cada empresa; cada empresa deve ter seu próprio certificado</li>
      <li>Salve o certificado ANTES de tentar fazer o primeiro download</li>
      <li>Se o certificado expirar, atualize-o aqui</li>
      <li>Nunca compartilhe o arquivo do certificado ou sua senha</li>
      <li>Se esquecer a senha, entre em contato com a autoridade certificadora</li>
    </ul>
    
    <h2>ABA: PORTAL</h2>
    
    <h3>Modo de Acesso</h3>
    <ul>
      <li><b>Certificado Digital</b>: Usa o certificado configurado na aba anterior (recomendado)</li>
      <li><b>Credenciais (Login/Senha)</b>: Usa login e senha do portal</li>
    </ul>
    
    <h3>Se Usar Credenciais</h3>
    <ol>
      <li>Selecione <b>"Credenciais (Login/Senha)"</b></li>
      <li>Digite o <b>Login</b> (geralmente CPF ou CNPJ)</li>
      <li>Digite a <b>Senha</b></li>
      <li>Clique em <b>"Salvar Credenciais"</b></li>
    </ol>
    
    <h3>URL do Portal</h3>
    <p>A URL do portal está travada nesta versão (não pode ser alterada). Ela aponta para o portal oficial da prefeitura.</p>
    
    <h3>Pasta de Downloads</h3>
    <p>A pasta de downloads também está travada nesta versão. Os arquivos serão salvos sempre no mesmo local.</p>
    
    <h3>Navegador Oculto (Headless)</h3>
    <ul>
      <li><b>Desativado</b>: O navegador abre visualmente e você pode acompanhar o processo</li>
      <li><b>Ativado</b>: O navegador funciona em segundo plano (mais rápido, mas menos controle visual)</li>
      <li><b>Dica</b>: Use modo visível primeiro para testar; ative headless depois que tudo estiver funcionando</li>
    </ul>
    
    <h2>ABA: SISTEMA</h2>
    
    <h3>Parâmetros Gerais</h3>
    <ul>
      <li><b>Timeout de Conexão</b>: Tempo máximo de espera para conectar ao portal</li>
      <li><b>Tempo de Espera entre Tentativas</b>: Intervalo entre tentativas de reconexão</li>
      <li><b>Máximo de Tentativas</b>: Quantas vezes o sistema tenta reconectar</li>
    </ul>
    
    <h3>Banco de Dados</h3>
    <ul>
      <li><b>Status da Conexão</b>: Mostra se o banco de dados local está funcionando</li>
      <li><b>Caminho do Banco</b>: Localização do arquivo de banco de dados</li>
    </ul>
    
    <h2>Passo a Passo Completo de Configuração Inicial</h2>
    <ol>
      <li>Vá para a aba <b>CERTIFICADO</b></li>
      <li>Procure e selecione seu arquivo de certificado (.pfx ou .p12)</li>
      <li>Digite a senha do certificado</li>
      <li>Clique em <b>"Salvar Certificado"</b></li>
      <li>Vá para a aba <b>PORTAL</b></li>
      <li>Verifique se <b>"Certificado Digital"</b> está selecionado</li>
      <li>Clique em <b>"Testar Conexão"</b> para verificar se tudo está funcionando</li>
      <li>Se o teste passar, você está pronto para fazer o primeiro download!</li>
    </ol>
    
    <h2>Dicas Importantes</h2>
    <ul>
      <li>Configure o certificado ANTES de tentar fazer qualquer download</li>
      <li>Se a conexão falhar, verifique a senha do certificado</li>
      <li>Se ainda assim não funcionar, consulte os Logs para mais detalhes</li>
      <li>Cada empresa tem suas próprias configurações; selecione a empresa antes de configurar</li>
      <li>Se o certificado expirar, você precisará atualizá-lo aqui</li>
    </ul>
    
    <h2>Próximos Passos</h2>
    <p>Após configurar o certificado e portal, você está pronto para usar o módulo <b>Download</b> 
    para buscar seus primeiros documentos.</p>
    """,
    
    "licencas": """
    <h1>Licenças - Gerenciamento de Ativação</h1>
    <p>Este módulo gerencia a ativação e renovação de licenças do software. 
    Aqui você cadastra o comprador, acompanha o período de teste e realiza pagamentos via Pix.</p>
    
    <h2>Estados de Licença</h2>
    
    <h3>Não Cadastrado</h3>
    <p>Nenhum comprador foi cadastrado ainda. O sistema está em modo de teste limitado.</p>
    
    <h3>Teste Ativo (7 dias)</h3>
    <p>O software está em período de teste gratuito. Você pode usar todas as funcionalidades, 
    mas o acesso ao portal será bloqueado após 7 dias se não ativar uma licença.</p>
    
    <h3>Licença Ativa</h3>
    <p>Você tem uma licença válida e pode usar o software sem restrições.</p>
    
    <h3>Licença Expirada</h3>
    <p>Sua licença expirou. Os XMLs já baixados continuam disponíveis, 
    mas o sistema bloqueia novas capturas no portal até renovar.</p>
    
    <h2>Seção: Cadastro do Comprador</h2>
    
    <h3>Campos Obrigatórios</h3>
    <ul>
      <li><b>Nome</b>: Nome completo de quem está comprando</li>
      <li><b>CPF/CNPJ</b>: Documento válido</li>
      <li><b>E-mail</b>: Para receber confirmações</li>
      <li><b>Telefone</b>: Para contato (opcional mas recomendado)</li>
    </ul>
    
    <h3>Como Cadastrar</h3>
    <ol>
      <li>Preencha todos os campos obrigatórios</li>
      <li>Clique em <b>"Salvar Cadastro"</b></li>
      <li>Uma mensagem de sucesso indicará que o cadastro foi salvo</li>
      <li>Sua máquina será identificada automaticamente</li>
    </ol>
    
    <h2>Seção: Compra de Licenças</h2>
    
    <h3>Tabela de Preços</h3>
    <ul>
      <li><b>1 máquina</b>: Preço base</li>
      <li><b>2-5 máquinas</b>: Desconto de 10%</li>
      <li><b>6-10 máquinas</b>: Desconto de 20%</li>
      <li><b>11+ máquinas</b>: Desconto de 30%</li>
    </ul>
    
    <h3>Como Comprar</h3>
    <ol>
      <li>Selecione a quantidade de máquinas desejada</li>
      <li>O preço será calculado automaticamente com desconto se aplicável</li>
      <li>Clique em <b>"Gerar Pix"</b></li>
      <li>Um código Pix será gerado</li>
      <li>Copie o código ou escaneie o QR code com seu banco</li>
      <li>Realize o pagamento via Pix</li>
      <li>Clique em <b>"Atualizar Status"</b> para confirmar o pagamento</li>
    </ol>
    
    <h2>Pagamento via Pix</h2>
    
    <h3>Copiando o Código Pix</h3>
    <ol>
      <li>Clique em <b>"Copiar Código Pix"</b></li>
      <li>Abra seu aplicativo bancário</li>
      <li>Selecione "Transferência Pix" ou "Pagar com Pix"</li>
      <li>Cole o código copiado</li>
      <li>Confirme o pagamento</li>
    </ol>
    
    <h3>Escaneando o QR Code</h3>
    <ol>
      <li>Abra seu aplicativo bancário</li>
      <li>Selecione "Ler QR Code"</li>
      <li>Aponte a câmera para o QR code exibido na tela</li>
      <li>Confirme o pagamento</li>
    </ol>
    
    <h2>Dicas Importantes</h2>
    <ul>
      <li>O período de teste é de 7 dias a partir do primeiro acesso</li>
      <li>Você pode comprar licenças para múltiplas máquinas</li>
      <li>Cada máquina é identificada automaticamente</li>
      <li>Se mudar de computador, você pode usar a mesma licença em até 5 máquinas diferentes</li>
      <li>Após o pagamento, clique em <b>"Atualizar Status"</b> para ativar a licença</li>
      <li>Se o pagamento não for confirmado, verifique a conexão com a internet</li>
    </ul>
    """,
    
    "limpeza_backup": """
    <h1>Limpeza e Backup - Gerenciamento de Dados</h1>
    <p>Este módulo oferece ferramentas para limpeza de arquivos temporários, criação de backups e restauração de dados.</p>
    
    <h2>Abas Disponíveis</h2>
    
    <h2>ABA: LIMPEZA DE ARQUIVOS</h2>
    
    <h3>O que é Limpeza?</h3>
    <p>Remove arquivos temporários e cache que podem estar ocupando espaço em disco.</p>
    
    <h3>Tipos de Limpeza</h3>
    <ul>
      <li><b>Cache de Municipios</b>: Remove cache de dados de municipios</li>
      <li><b>Arquivos Temporários</b>: Remove arquivos .tmp e similares</li>
      <li><b>Logs Antigos</b>: Remove logs com mais de 30 dias</li>
    </ul>
    
    <h3>Como Fazer Limpeza</h3>
    <ol>
      <li>Selecione a empresa (opcional)</li>
      <li>Escolha o tipo de limpeza desejada</li>
      <li>Clique em <b>"Executar Limpeza"</b></li>
      <li>Acompanhe o progresso na barra de progresso</li>
      <li>Uma mensagem indicará quantos arquivos foram removidos</li>
    </ol>
    
    <h2>ABA: CRIAR BACKUP</h2>
    
    <h3>O que é Backup?</h3>
    <p>Um backup é uma cópia completa de todos os seus dados. Use regularmente para proteger suas informações.</p>
    
    <h3>Como Criar Backup</h3>
    <ol>
      <li>Selecione a empresa (ou deixe em branco para todas)</li>
      <li>Escolha o período (opcional)</li>
      <li>Clique em <b>"Criar Backup"</b></li>
      <li>Escolha o local para salvar o arquivo ZIP</li>
      <li>Acompanhe o progresso</li>
      <li>Um arquivo .zip será criado com todos os dados</li>
    </ol>
    
    <h3>Dicas sobre Backup</h3>
    <ul>
      <li>Faça backup regularmente (pelo menos uma vez por mês)</li>
      <li>Guarde os backups em local seguro (nuvem, HD externo, etc.)</li>
      <li>Teste a restauração ocasionalmente para garantir que o backup está funcionando</li>
      <li>Backups maiores podem levar alguns minutos</li>
    </ul>
    
    <h2>ABA: RESTAURAR BACKUP</h2>
    
    <h3>Como Restaurar um Backup</h3>
    <ol>
      <li>Clique em <b>"Selecionar Arquivo de Backup"</b></li>
      <li>Escolha o arquivo .zip do backup que deseja restaurar</li>
      <li>Revise os dados que serão restaurados</li>
      <li>Clique em <b>"Restaurar"</b></li>
      <li>Acompanhe o progresso</li>
      <li>Uma mensagem indicará que a restauração foi concluída</li>
    </ol>
    
    <h3>ATENÇÃO: Restauração</h3>
    <ul>
      <li>A restauração sobrescreverá os dados atuais</li>
      <li>Faça backup dos dados atuais ANTES de restaurar</li>
      <li>Após restaurar, você pode precisar reiniciar o programa</li>
    </ul>
    
    <h2>ABA: HISTÓRICO DE OPERAÇÕES</h2>
    
    <h3>O que é o Histórico?</h3>
    <p>Mostra um registro de todas as operações de limpeza, backup e restauração realizadas.</p>
    
    <h3>Informações Exibidas</h3>
    <ul>
      <li><b>Data/Hora</b>: Quando a operação foi realizada</li>
      <li><b>Tipo</b>: Limpeza, Backup ou Restauração</li>
      <li><b>Empresa</b>: Qual empresa foi afetada</li>
      <li><b>Status</b>: Sucesso ou Erro</li>
      <li><b>Detalhes</b>: Informações adicionais sobre a operação</li>
    </ul>
    
    <h2>Dicas Importantes</h2>
    <ul>
      <li>Faça limpeza regularmente para manter o sistema rápido</li>
      <li>Faça backup antes de fazer limpezas grandes</li>
      <li>Guarde backups em local seguro e separado do computador</li>
      <li>Teste restaurações ocasionalmente</li>
      <li>Se algo der errado, você sempre terá um backup para restaurar</li>
    </ul>
    """
}

def topic_title(topic: str) -> str:
    return TOPIC_TITLES.get(topic or "geral", "Ajuda")


def topic_html(topic: str) -> str:
    key = topic if topic in TOPIC_HTML else "geral"
    return TOPIC_HTML[key]


def build_topics_index_html() -> str:
    items = []
    ordered = ["geral", "dashboard", "empresas", "download", "xmls", "manifestacao", "logs", "relatorios", "configuracoes", "licencas", "limpeza_backup"]
    for key in ordered:
        items.append(f"<li><b>{escape(topic_title(key))}</b></li>")
    return "<h2>Seções disponíveis</h2><ul>" + "".join(items) + "</ul>"
