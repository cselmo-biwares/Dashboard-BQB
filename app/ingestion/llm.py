"""LLM client and prompts for classifying items against the topic tree.

Ported from the prototype notebook (Tagueo/cargar_biwares_backup.ipynb), split into two
distinct operations (see the plan): classification is always append-only (can add new
leaves, never touches existing nodes/leaves), while restructuring only reshuffles nodes
and never changes the set of leaves.

The three system prompts are user-editable from the front (see app.routers.prompts):
`get_prompt` reads the current value fresh from the DB on every call (falling back to
the hardcoded default below when there's no override), so edits take effect on the very
next LLM call — no restart, no caching to invalidate.
"""

import json
import logging

from anthropic import AnthropicBedrock
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BedrockSettings
from app.db.models import PromptOverride

logger = logging.getLogger(__name__)

PROMPT_KEY_CLASSIFY_CONVERSATION = "classify_conversation"
PROMPT_KEY_CLASSIFY_DOCUMENT = "classify_document"
PROMPT_KEY_RESTRUCTURE = "restructure"
PROMPT_KEY_ROOT_CAUSE = "root_cause"


def create_llm_client(settings: BedrockSettings) -> AnthropicBedrock:
    """Create the AnthropicBedrock client from settings."""
    return AnthropicBedrock(
        aws_access_key=settings.access_key_id,
        aws_secret_key=settings.secret_access_key,
        aws_region=settings.region_name,
    )


DEFAULT_PROMPT_CLASSIFY_CONVERSATION = """Sos un clasificador de temas para un sistema de soporte de una empresa
de transporte marítimo (Buquebus). Ya existe un árbol jerárquico de temas construido a partir de la documentación.

Recibís:
1. El árbol de temas actual (en JSON).
2. La conversación completa entre el usuario y el asistente (preguntas y respuestas).

Tu trabajo es identificar qué consultas hace el usuario al asistente. Para cada consulta la idea
es que le detectes sobre qué tema(s) del árbol preguntó el usuario. Adicionalmente para cada
consulta evaluar si la fue resuelta satisfactoriamente según la respuesta del asistente. No estás
evaluando veracidad, estás evaluando si respondió o no.

Reglas MUY IMPORTANTES:
- NO reestructures el árbol existente: no fusiones, no partas, no renombres, no muevas
  ni elimines nada de lo que ya existe. Esta pasada es de solo lectura sobre el árbol,
  salvo por la excepción del punto siguiente.
- Si el usuario preguntó sobre un tema que NO está representado en ninguna hoja existente,
  definí una hoja nueva para ese tema y ubicala en la rama existente que corresponda
  (o como hija directa de "root" si no encaja en ninguna rama actual).
- La conversación puede tener más de una consulta: identificá los grupos de mensaje que componten cada consulta.
- Cada consulta puede referirse a mas de un tema: implica que cada conversación puede quedar vinculada a más de un tema.
- Para cada hoja, evaluá el estado de resolución de ESE tema puntual (no de la
  conversación entera) mirando ÚNICAMENTE el contenido de la respuesta del asistente
  frente a la consulta del usuario:
    - "resolved": el asistente dio una respuesta clara y completa a la consulta sobre ese tema.
    - "partial": el asistente respondió algo relacionado pero de forma incompleta o ambigua.
    - "unresolved": el asistente no pudo responder, dio información incorrecta/genérica,
      derivó a otro canal sin resolver la consulta, o el usuario expresó CON PALABRAS
      que quedó insatisfecho.
    - "unknown": la conversación se corta antes de que el asistente llegue a responder
      la consulta sobre ese tema (no hay respuesta que evaluar).
  - REGLA CRÍTICA: que el usuario no vuelva a escribir después de la respuesta NO es una
    señal de nada — es el comportamiento más común en este tipo de chats y generalmente
    significa que ya no tenía más dudas. NUNCA uses el silencio o abandono del usuario
    para inferir "partial", "unresolved" ni "unknown". Evaluá exclusivamente si LA
    RESPUESTA que dio el asistente resuelve lo que se preguntó, esté o no esté esa
    respuesta seguida de más mensajes del usuario.
- Si el usuario no preguntó por nada identificable (saludo, sin contenido temático),
  devolvé una lista vacía de temas.

Formato de salida (JSON, sin texto adicional, sin backticks):
{
  "topics": [
    {
      "leaf_path": "Ruta > A > Hoja1",
      "resolution": "resolved" | "partial" | "unresolved" | "unknown",
      "reasoning": "breve justificación en una frase"
    }
  ],
  "new_leaves": [
    {
      "parent_path": "Ruta > A",
      "name": "Nombre de la hoja nueva"
    }
  ]
}
- "topics": una entrada por cada hoja (existente o nueva) donde cae la conversación.
- "new_leaves": únicamente las hojas que hubo que crear porque no existían.
- Si no hay hojas nuevas, "new_leaves" debe ser una lista vacía.
"""

DEFAULT_PROMPT_CLASSIFY_DOCUMENT = """Sos un clasificador de temas para un sistema RAG de una empresa de buses
(BQB). Ya existe un árbol jerárquico de temas construido a partir de la documentación.

Recibís:
1. El árbol de temas actual (en JSON).
2. El contenido de un documento nuevo (.md).

Tu trabajo es identificar en qué hoja(s) del árbol encaja este documento.

Reglas MUY IMPORTANTES:
- NO reestructures el árbol existente: no fusiones, no partas, no renombres, no muevas
  ni elimines nada de lo que ya existe. Esta pasada es de solo lectura sobre el árbol,
  salvo por la excepción del punto siguiente.
- Si el documento trata un tema que NO está representado en ninguna hoja existente,
  definí una hoja nueva para ese tema y ubicala en la rama existente que corresponda
  (o como hija directa de "root" si no encaja en ninguna rama actual).
- El documento puede tocar más de un tema: puede caer en más de una hoja (existentes,
  nuevas, o una combinación de ambas).

Formato de salida (JSON, sin texto adicional, sin backticks):
{
  "leaf_paths": ["Ruta > A > Hoja1", "Ruta > B > Hoja2"],
  "new_leaves": [
    {
      "parent_path": "Ruta > A",
      "name": "Nombre de la hoja nueva"
    }
  ]
}
- "leaf_paths": rutas completas (formato "Padre > Subtema > Hoja", separadas por " > ",
  sin incluir "root") de TODAS las hojas -existentes o nuevas- donde cae el documento.
- "new_leaves": únicamente las hojas que hubo que crear porque no existían. Si una hoja
  nueva está en "leaf_paths", su ruta completa (parent_path + " > " + name) debe coincidir.
- Si no hay hojas nuevas, "new_leaves" debe ser una lista vacía.
"""

DEFAULT_PROMPT_RESTRUCTURE = """Sos un editor de taxonomías para un sistema de soporte de una empresa de
buses (BQB). Recibís la FORMA del árbol de temas actual (nodos y nombres de hojas, sin contenido).

Tu trabajo es reorganizar los NODOS del árbol (agrupamiento/jerarquía) para que quede más claro y
coherente. Podés crear, fusionar, renombrar, mover o eliminar nodos libremente, y podés cambiar
bajo qué nodo cuelga cada hoja.

Regla MUY IMPORTANTE, sin excepciones: el CONJUNTO de hojas (por nombre) debe ser exactamente el
mismo antes y después. No podés crear, eliminar, renombrar, fusionar ni partir ninguna hoja — solo
reposicionarla bajo otro nodo. Si esta regla no se cumple, tu respuesta será rechazada.

Formato del árbol (JSON):
  {
    "name": "root",
    "children": [
      {
        "name": "<nombre del nodo u hoja>",
        "type": "node" | "leaf",
        "children": [...]   // solo si type == "node"
      }
    ]
  }

Devolvé SIEMPRE el árbol JSON completo reorganizado (no un diff), sin texto adicional, sin
backticks, sin comentarios. Solo el JSON.
"""


DEFAULT_PROMPT_ROOT_CAUSE = """Sos un analista de causas raíz para un sistema de soporte de una empresa de
transporte marítimo (Buquebus). Vas a recibir un tema puntual del árbol de temas, un estado de resolución
("partial" o "unresolved"), y una lista de justificaciones ("reasoning") que otro modelo escribió al
clasificar cada conversación individual con ese estado para ese tema.

Tu trabajo es leer todas esas justificaciones y detectar el patrón: por qué la MAYORÍA de estos casos
terminan con ese estado de resolución. No repitas cada justificación individual, sintetizá la causa
común. Si hay más de un patrón relevante, identificá el principal y hasta dos secundarios.

Formato de salida (JSON, sin texto adicional, sin backticks):
{
  "main_cause": "título breve de la causa principal (una frase corta)",
  "explanation": "2 a 4 oraciones explicando el patrón principal, en español, tono directo y accionable",
  "secondary_causes": ["causa secundaria 1", "causa secundaria 2"]
}
- "secondary_causes" puede ser una lista vacía si no hay un segundo patrón claro.
"""


DEFAULT_PROMPTS: dict[str, str] = {
    PROMPT_KEY_CLASSIFY_CONVERSATION: DEFAULT_PROMPT_CLASSIFY_CONVERSATION,
    PROMPT_KEY_CLASSIFY_DOCUMENT: DEFAULT_PROMPT_CLASSIFY_DOCUMENT,
    PROMPT_KEY_RESTRUCTURE: DEFAULT_PROMPT_RESTRUCTURE,
    PROMPT_KEY_ROOT_CAUSE: DEFAULT_PROMPT_ROOT_CAUSE,
}


async def get_prompt(session: AsyncSession, key: str) -> str:
    """Get the current system prompt for `key`.

    The front-edited override if there is one, otherwise the hardcoded default. Always
    reads fresh — no caching.
    """
    override = await session.get(PromptOverride, key)
    return override.content if override is not None else DEFAULT_PROMPTS[key]


def _call_model(client: AnthropicBedrock, settings: BedrockSettings, system_prompt: str, user_message: str) -> dict:
    """Call the LLM with a system/user prompt pair and parse the JSON response."""
    response = client.messages.create(
        model=settings.model,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"El modelo no devolvió JSON válido:\n{raw}") from e


def classify_conversation(
    client: AnthropicBedrock,
    settings: BedrockSettings,
    tree: dict,
    conversation_id: int,
    full_text: str,
    system_prompt: str = DEFAULT_PROMPT_CLASSIFY_CONVERSATION,
) -> dict:
    """Classify a conversation's full text against the existing tree, with per-topic resolution."""
    user_message = f"""Árbol actual:
{json.dumps(tree, ensure_ascii=False, indent=2)}

Conversación completa #{conversation_id}:
\"\"\"
{full_text[:10000]}
\"\"\"

Devolvé el JSON con los temas y su estado de resolución."""
    return _call_model(client, settings, system_prompt, user_message)


def classify_document(
    client: AnthropicBedrock,
    settings: BedrockSettings,
    tree: dict,
    doc_name: str,
    doc_text: str,
    system_prompt: str = DEFAULT_PROMPT_CLASSIFY_DOCUMENT,
) -> dict:
    """Classify a document's content against the existing tree."""
    user_message = f"""Árbol actual:
{json.dumps(tree, ensure_ascii=False, indent=2)}

Documento nuevo: "{doc_name}"

Contenido del documento:
\"\"\"
{doc_text[:12000]}
\"\"\"

Devolvé el JSON con las hojas correspondientes."""
    return _call_model(client, settings, system_prompt, user_message)


def summarize_root_cause(
    client: AnthropicBedrock,
    settings: BedrockSettings,
    topic_path: str,
    resolution: str,
    reasoning_samples: list[str],
    system_prompt: str = DEFAULT_PROMPT_ROOT_CAUSE,
) -> dict:
    """Synthesize why most conversations in a topic ended up with a given (partial/unresolved) resolution."""
    samples_block = "\n".join(f"- {r}" for r in reasoning_samples)
    user_message = f"""Tema: "{topic_path}"
Estado de resolución analizado: "{resolution}"
Cantidad de justificaciones recibidas: {len(reasoning_samples)}

Justificaciones:
{samples_block}

Devolvé el JSON con el análisis de causa raíz."""
    return _call_model(client, settings, system_prompt, user_message)


def restructure_tree(
    client: AnthropicBedrock,
    settings: BedrockSettings,
    tree_structure: dict,
    instruction: str | None = None,
    system_prompt: str = DEFAULT_PROMPT_RESTRUCTURE,
) -> dict:
    """Reorganize the node hierarchy of the tree, keeping the leaf set unchanged."""
    instruction_block = f"\n\nInstrucción adicional del usuario: {instruction}" if instruction else ""
    user_message = f"""Forma actual del árbol:
{json.dumps(tree_structure, ensure_ascii=False, indent=2)}
{instruction_block}

Devolvé la versión reorganizada."""
    return _call_model(client, settings, system_prompt, user_message)
