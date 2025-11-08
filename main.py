import json
import requests

import streamlit as st

from time import sleep
from datetime import datetime as dt, timedelta as td
    
def plota_link(ata):
    n_ata = ata[0]
    nome_unidade = ata[1]
    fornecedor = ata[2]
    id_pncp = ata[3]
    
    st.write(f'[Ata n° {n_ata} de {nome_unidade} com {fornecedor}]({f'https://pncp.gov.br/pncp-api/v1/orgaos/{id_pncp.split('-')[0]}/compras/{id_pncp.split('/')[1].split('-')[0]}/{id_pncp.split('-')[2].split('/')[0].lstrip('0')}/atas/{id_pncp.split('-')[-1].lstrip('0')}/arquivos/{id_pncp.split('-')[1]}'})')

def acha_servico():
    st.session_state['atas'] = []
    try:
        codigoServico = st.session_state['servicos'][st.session_state['nomeServico']]
        
        i = 1
        while True:
            try:
                response = requests.get(f'https://dadosabertos.compras.gov.br/modulo-arp/2_consultarARPItem?pagina={i}&tamanhoPagina=500&dataVigenciaInicialMin={(dt.today() - td(days=360)).strftime("%Y-%m-%d")}&dataVigenciaInicialMax={(dt.today()).strftime("%Y-%m-%d")}&codigoItem={codigoServico}').json()
                st.session_state['atas'] += response['resultado']
            except KeyError:
                print(response.json())
                sleep(1)
                continue
            
            if response['paginasRestantes'] == 0:
                break
            i += 1
            sleep(0.1)
    except KeyError:
        pass

def acha_material():
    st.session_state['atas'] = []
    try:
        codigoPdm = st.session_state['materiais'][st.session_state['nomePdm']]
            
        i = 1
        while True:
            try:
                response = requests.get(f'https://dadosabertos.compras.gov.br/modulo-arp/2_consultarARPItem?pagina=1&tamanhoPagina=500&dataVigenciaInicialMin={(dt.today() - td(days=360)).strftime("%Y-%m-%d")}&dataVigenciaInicialMax={(dt.today()).strftime("%Y-%m-%d")}&codigoPdm={codigoPdm}').json()
                st.session_state['atas'] += response['resultado']
            except KeyError:
                print(response.json())
                sleep(1)
                continue
            
            if response['paginasRestantes'] == 0:
                break
            i += 1
            sleep(0.1)
    except KeyError:
        pass

if 'initialized' not in st.session_state:
    st.cache_data.clear()
    st.cache_resource.clear()
    
    vrf1 = st.text_input(st.secrets.pergunta_secreta.pergunta1)
    
    if vrf1:
        
        if (vrf1.lower() in st.secrets.pergunta_secreta.vrf1):
            st.session_state['initialized'] = True
            st.rerun()
        
        else:
            st.write('Parece que você não respondeu a pergunta de segurança corretamente.')
            st.write('Sinto muito, mas esta aplicação não é para você...')
            st.stop()



if 'initialized' in st.session_state:
    
    st.title('Buscador de adesões')
    
    tipo = st.selectbox(
        'Está buscando material ou serviço, meu consagrado?',
        ['Material', 'Serviço'],
        index=None,
        placeholder='Material ou Serviço?'
    )

    if tipo=='Material':
        
        with open('catalogo_pdm.json', 'r') as f:
            st.session_state['materiais'] = json.load(f)
        
        st.selectbox(
            'Pesquise o que você está procurando:',
            sorted(set(st.session_state['materiais'].keys())),
            index=None,
            placeholder='Escolhe teu material aí...',
            key='nomePdm',
            on_change=acha_material
        )
        
    elif tipo=='Serviço':
        
        with open('catalogo_servicos.json', 'r') as f:
            st.session_state['servicos'] = json.load(f)
            
        st.selectbox(
            'Pesquise o que você está procurando:',
            sorted(set(st.session_state['servicos'].keys())),
            index=None,
            key='nomeServico',
            on_change=acha_servico,
            placeholder='Escolhe teu serviço aí...'
        )

    if 'atas' in st.session_state:
        atas_info = set([(i['numeroAtaRegistroPreco'], i['nomeUnidadeGerenciadora'], i['nomeRazaoSocialFornecedor'], i['numeroControlePncpAta']) for i in st.session_state.atas if i['maximoAdesao'] != 0])
        
        if len(atas_info) == 0:
            st.write('Sinto muito, nenhuma ata foi encontrada...')
        else:
            for ata in atas_info:
                plota_link(ata)