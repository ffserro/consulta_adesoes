import json
import base64
import asyncio
from datetime import datetime as dt, timedelta as td
from typing import Dict, List, Optional, Tuple

import aiohttp
import streamlit as st

API_URL = "https://dadosabertos.compras.gov.br/modulo-arp/2_consultarARPItem"
MAX_CONCURRENCY = 4
DATE_RANGE_DAYS = 360
PAGE_SIZE = {"Material": 500, "Serviço": 500}


st.set_page_config(
    page_title="Buscador de Adesões",
    page_icon="⚓",
    layout="wide",
)

CUSTOM_CSS = """
<style>
    .main {
        background: radial-gradient(120% 120% at 0% 0%, #0f172a 0%, #0b1220 45%, #0a0f1d 100%);
        color: #e2e8f0;
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    }
    .block-container {
        padding: 2rem 3rem 4rem 3rem;
    }
    .stSelectbox label, .stSlider label, .stTextInput label {
        font-weight: 600;
        color: #e2e8f0;
    }
    .metric-card {
        background: #11182b;
        border: 1px solid #1f2937;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    }
    .result-card {
        background: #0f1627;
        border-radius: 10px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.55rem;
        border: 1px solid #1f2937;
        box-shadow: 0 6px 24px rgba(0,0,0,0.28);
    }
    a {
        color: #76c7ff !important;
        text-decoration: none !important;
        font-weight: 600;
    }
    a:hover {
        color: #a3d9ff !important;
        text-decoration: underline !important;
    }
    .status-text {
        color: #cbd5e1;
        font-size: 0.95rem;
        margin-bottom: 0.25rem;
    }
</style>
"""


@st.cache_data
def load_catalog(path: str) -> Dict[str, str]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_ata_url(identifier: str) -> str:
    """Monta a URL da ata a partir do identificador retornado pela API."""
    try:
        orgao = identifier.split("-")[0]
        compra = identifier.split("/")[1].split("-")[0]
        year = identifier.split("-")[2].split("/")[0].lstrip("0") or "0"
        ata = identifier.split("-")[-1].split("/")[0].lstrip("0") or "0"
        arquivo = identifier.split("-")[1]
        return (
            f"https://pncp.gov.br/pncp-api/v1/orgaos/{orgao}"
            f"/compras/{compra}/{year}/atas/{ata}/arquivos/{arquivo}"
        )
    except Exception:
        return ""


def normalize_item(item: Dict) -> Optional[Tuple[str, str, str, str, str]]:
    """Prepara dados da ata para exibição e evita entradas sem adesão."""
    if item.get("maximoAdesao", 0) == 0:
        return None

    numero_ata = item.get("numeroAtaRegistroPreco", "Ata não informada")
    unidade = item.get("nomeUnidadeGerenciadora", "Unidade não informada")
    fornecedor = item.get("nomeRazaoSocialFornecedor", "Fornecedor não informado")
    identificador = item.get("numeroControlePncpAta", "")
    url = build_ata_url(identificador)

    return numero_ata, unidade, fornecedor, identificador, url


def parse_remaining_pages(raw_value) -> int:
    """Garante que paginasRestantes seja tratado como inteiro seguro."""
    try:
        return max(int(raw_value or 0), 0)
    except (TypeError, ValueError):
        return 0


def extract_uasg(item: Dict) -> Optional[str]:
    """Tenta extrair o código UASG do item retornado pela API."""
    candidates = [
        "uasg",
        "codigoUasg",
        "codigoUnidadeGerenciadora",
        "codigoUnidadeGestora",
        "codigoUG",
    ]
    for key in candidates:
        value = item.get(key)
        if value:
            return str(value)
    return None


async def fetch_page(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    page: int,
    base_params: Dict[str, str],
) -> Dict:
    params = {**base_params, "pagina": page}
    async with semaphore:
        async with session.get(API_URL, params=params) as response:
            response.raise_for_status()
            return await response.json()


async def search_async(
    tipo: str,
    codigo: str,
    results_container: st.delta_generator.DeltaGenerator,
    status_placeholder: st.delta_generator.DeltaGenerator,
    federal_only: bool,
    uasg_sphere: Dict[str, str],
    max_concurrency: int = MAX_CONCURRENCY,
) -> List[Dict]:
    """Executa a busca de forma assíncrona, exibindo resultados conforme chegam."""
    timeout = aiohttp.ClientTimeout(total=15)
    semaphore = asyncio.Semaphore(max_concurrency)
    base_params = {
        "tamanhoPagina": PAGE_SIZE.get(tipo, 120),
        "dataVigenciaInicialMin": (dt.today() - td(days=DATE_RANGE_DAYS)).strftime("%Y-%m-%d"),
        "dataVigenciaInicialMax": dt.today().strftime("%Y-%m-%d"),
    }
    if tipo == "Material":
        base_params["codigoPdm"] = codigo
    else:
        base_params["codigoItem"] = codigo

    connector = aiohttp.TCPConnector(limit=None, ssl=False)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        first_page = await fetch_page(session, semaphore, 1, base_params)
        total_pages = 1 + parse_remaining_pages(first_page.get("paginasRestantes"))

        seen = set()
        results: List[Dict] = []

        def render_payload(payload: Dict) -> None:
            for raw in payload.get("resultado", []):
                uasg_code = extract_uasg(raw)
                if federal_only:
                    if not uasg_code:
                        continue
                    if uasg_sphere.get(str(uasg_code)) != "F":
                        continue

                normalized = normalize_item(raw)
                if not normalized:
                    continue
                key = normalized[3]
                if key in seen:
                    continue
                seen.add(key)
                results.append(raw)

                numero, unidade, fornecedor, _, url = normalized
                results_container.markdown(
                    f"""
                    <div class="result-card">
                        <div class="status-text">Ata {numero} • {unidade}</div>
                        <div><a href="{url}" target="_blank">Visualizar documento – {fornecedor}</a></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        render_payload(first_page)

        if total_pages == 1:
            status_placeholder.success("Busca concluída.")
            return results

        tasks = [
            asyncio.create_task(fetch_page(session, semaphore, page, base_params))
            for page in range(2, total_pages + 1)
        ]

        for index, task in enumerate(asyncio.as_completed(tasks), start=2):
            try:
                payload = await task
                render_payload(payload)
                status_placeholder.info(f"Processando páginas ({index}/{total_pages})…")
            except Exception:
                status_placeholder.warning(
                    "Falha ao carregar uma das páginas. Retentativa não disponível."
                )

        status_placeholder.success("Busca concluída.")
        return results


def run_search(
    tipo: str,
    codigo: str,
    federal_only: bool,
    uasg_sphere: Dict[str, str],
) -> None:
    results_container = st.container()
    status_placeholder = st.empty()

    with st.spinner("Consultando dados, por favor aguarde um momento…"):
        try:
            asyncio.run(
                search_async(
                    tipo,
                    codigo,
                    results_container,
                    status_placeholder,
                    federal_only=federal_only,
                    uasg_sphere=uasg_sphere,
                )
            )
        except Exception:
            status_placeholder.error(
                "Não foi possível concluir a consulta agora, provavelmente por instabilidades no Compras.gov. Tente novamente em instantes."
            )

    if not status_placeholder:
        status_placeholder.info("Nenhum resultado encontrado para este critério.")

with open('acanto.png', 'rb') as f:
    acanto = f.read()
acanto = base64.b64encode(acanto).decode()


def main() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # st.title("Buscador de Adesões 2.0")
    st.markdown(
    f"""
    <div style="
        display: flex; 
        align-items: center;
        gap: 12px;
    ">
        <img src="data:image/png;base64,{acanto}" style="height: 2em;">
        <h1 style="margin: 0;">Buscador de Adesões 2.0</h1>
        
    </div>
    """,
    unsafe_allow_html=True
)
    st.caption("Consulta inteligente às atas de registro de preços do Compras.gov.br.")

    st.write(
        "Selecione o tipo de item, escolha o código desejado e encontre atas para adesão."
    )

    tipo = st.selectbox(
        "Tipo de item",
        ["Material", "Serviço"],
        index=None,
        placeholder="Selecione material ou serviço",
    )

    selected_label = None
    codigo = None
    federal_only = False
    uasg_sphere: Dict[str, str] = {}

    if tipo == "Material":
        materiais = load_catalog("catalogo_pdm.json")
        selected_label = st.selectbox(
            "Material",
            sorted(materiais.keys()),
            index=None,
            placeholder="Pesquise pelo nome do material",
        )
        if selected_label:
            codigo = materiais[selected_label]

    if tipo == "Serviço":
        servicos = load_catalog("catalogo_servicos.json")
        selected_label = st.selectbox(
            "Serviço",
            sorted(servicos.keys()),
            index=None,
            placeholder="Pesquise pelo nome do serviço",
        )
        if selected_label:
            codigo = servicos[selected_label]

    if selected_label:
        federal_only = st.checkbox("Buscar somente atas da esfera federal", value=True)
        if federal_only:
            uasg_sphere = load_catalog("esfera_uasg.json")

    start_button = st.button(
        "Buscar adesões", type="primary", use_container_width=True, disabled=not codigo
    )

    if start_button and tipo and codigo:
        st.session_state["atas"] = []
        run_search(tipo, codigo, federal_only, uasg_sphere)
    elif start_button and not codigo:
        st.warning("Selecione um item antes de iniciar a busca.")


if __name__ == "__main__":
    main()
