FROM python:3.8-slim

# git: para baixar o framework; build-essential: algumas bibliotecas compilam na instalação
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

# 1) Baixa o Heritage Connector em uma versão fixa (commit), para o resultado
#    ser sempre o mesmo. O código fica em /opt/heritage-connector.
ARG HC_COMMIT=77c994d7ba7253bd81140a2202bf8b03b6082e43
RUN git init /opt/heritage-connector \
    && cd /opt/heritage-connector \
    && git remote add origin https://github.com/TheScienceMuseum/heritage-connector.git \
    && git fetch --depth 1 origin ${HC_COMMIT} \
    && git checkout FETCH_HEAD

# 2) PyTorch só para CPU (evita baixar vários GB de bibliotecas de GPU)
RUN pip install --no-cache-dir torch==2.4.1 --extra-index-url https://download.pytorch.org/whl/cpu

# 3) Bibliotecas do framework + versões fixadas, porque o código é de 2021:
#    numpy<2 e rdflib<6 / rdflib-jsonld==0.6.1 (compatibilidade), spacy<3.8
#    (instalação no Python 3.8), elasticsearch<8 (casa com o Elasticsearch 7).
RUN pip install --no-cache-dir -r /opt/heritage-connector/requirements.txt \
    "elasticsearch<8" "rdflib<6" "rdflib-jsonld==0.6.1" "numpy<2" "spacy<3.8" pytest

# O Python encontra o pacote "heritageconnector" por aqui
ENV PYTHONPATH=/opt/heritage-connector

# Os scripts e os dados do museu ficam na pasta do projeto, ligada a /work
WORKDIR /work

CMD ["sleep", "infinity"]
