# Leitor de Códigos com Câmera Axis (RTSP)

Aplicação desktop em Python (Tkinter) para visualizar a câmera Axis via RTSP, realizar leitura de códigos de barras e QR em tempo real, e gerar relatório CSV continuamente durante a sessão de leitura.

## Principais Recursos
- Conexão à câmera via `RTSP` com `usuário` e `senha`.
- Visualização em tempo real do vídeo da câmera.
- Leitura iniciada/parada por botão, independente da conexão.
- Intervalo configurável entre leituras para evitar duplicadas indesejadas.
- Relatório CSV em tempo real com `Data`, `Horário`, `Código` e `Quantidade`.
- Tabela interna com leituras em tempo real (Treeview) para acompanhamento.
- Exportação manual opcional de relatório da sessão.

## Requisitos
- Python 3.8 ou superior.
- Câmera Axis acessível por RTSP.
- Dependências Python listadas em `requirements.txt`.

Para instalar as dependências:
```
pip install -r requirements.txt
```

Dependências:
- `pyzbar` (decodificação de códigos; inclui `zbar` em muitos ambientes Windows)
- `opencv-python` (captura de vídeo e processamento de imagem)
- `pillow` (conversão de imagem para Tkinter)

Observação: Em alguns ambientes, o `pyzbar` pode requerer `zbar` instalado no sistema. No Windows, os binários costumam vir junto; caso contrário, instale o `zbar` conforme sua plataforma.

## Como Executar
1. Abra um terminal na pasta `barcode_reader`.
2. Execute:
```
python axis_barcode_reader.py
```

## Uso da Interface
- Campo `IP da Câmera`: endereço IP ou host. Se não informar a porta, será usada `554` automaticamente.
- Campo `Usuário` e `Senha`: credenciais da câmera Axis.
- Campo `Intervalo (s)`: número de segundos de cooldown por código para reduzir duplicidade de eventos.
- Botão `Conectar Câmera`: inicia/encerra a conexão RTSP e a visualização em tempo real.
- Botão `Iniciar Leitura`: começa/pausa a leitura de códigos. A visualização permanece ativa mesmo pausada.
- Botão `Exportar Relatório`: grava um CSV da sessão atual sob demanda (além do CSV em tempo real).
- Área `Visualização`: mostra o vídeo da câmera dimensionado ao canvas.
- Área `Resultados`: log textual com eventos e mensagens.
- Tabela `Leituras (tempo real)`: insere uma linha por leitura com `Data`, `Horário`, `Código` e `Quantidade` acumulada daquele código.

## Relatórios CSV
- Em tempo real: ao iniciar a leitura, é criado um arquivo `axis_codes_live_YYYYMMDD-HHMMSS.csv` no diretório atual (`os.getcwd()`).
  - Cada leitura adiciona uma linha imediatamente: `Data`, `Horário`, `Código`, `Quantidade`.
  - O arquivo é atualizado a cada leitura (flush + fsync).
- Exportação manual: o botão `Exportar Relatório` gera um snapshot da sessão em `axis_codes_YYYYMMDD-HHMMSS.csv` com as mesmas colunas.

Observação sobre visualização do CSV:
- Editores simples (ex.: Notepad) recarregam o arquivo automaticamente quando ele muda.
- Excel geralmente não atualiza automaticamente CSV aberto; reabra o arquivo ou use Power Query com atualização.

## RTSP e Montagem da URL
A URL é montada como:
```
rtsp://USUARIO:SENHA@HOST:PORTA/axis-media/media.amp
```
- Se `PORTA` não for informada, assume-se `554`.
- Caracteres especiais em `usuário/senha` são codificados automaticamente.

## Acesso Externo (fora da rede local)
- Recomendado: VPN (WireGuard, OpenVPN, Tailscale, ZeroTier) para acessar como se estivesse na LAN.
- Alternativa: Port forwarding + DDNS no roteador; exponha uma porta TCP externa para `554` da câmera, com cuidado de segurança.
- Solução Axis: Secure Remote Access via Axis Companion/Camera Station para acesso seguro sem abrir portas diretamente.

## Boas Práticas e Segurança
- Use senhas fortes e desative acesso anônimo.
- Mantenha firmware da câmera atualizado.
- Prefira VPN/solução Axis para tráfego criptografado; RTSP puro não é criptografado.
- Restrinja o acesso por IP no firewall quando possível.

## Solução de Problemas
- Não conecta ao RTSP:
  - Verifique IP/usuário/senha.
  - Teste a URL em outra rede (CGNAT pode impedir port forwarding).
  - Confirme se a porta `554` está acessível e não bloqueada pelo firewall.
- Não lê códigos:
  - Garanta boa iluminação e foco.
  - Ajuste o posicionamento para o código ocupar área suficiente do frame.
  - Reduza o `Intervalo (s)` se estiver muito alto.
- CSV não “atualiza” no Excel:
  - Reabra o arquivo ou utilize um mecanismo de atualização (Power Query).

## Estrutura de Arquivos
- `axis_barcode_reader.py`: aplicação principal (UI, conexão RTSP, leitura de códigos, relatórios).
- `requirements.txt`: dependências Python.

## Execução Rápida
```
pip install -r requirements.txt
python axis_barcode_reader.py
```
