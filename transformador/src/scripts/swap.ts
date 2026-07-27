/**
 * El único JavaScript genérico de toda la aplicación.
 *
 * Aplica un FragmentUpdate al DOM y escucha el canal SSE. Se escribe una vez y sirve
 * para todas las pantallas — no hay un componente por pantalla porque no hay framework
 * de cliente.
 *
 * Ver 05-transformador-y-frontend.md.
 */

type FragmentAction =
  | 'replace' | 'update' | 'append' | 'prepend' | 'before' | 'after' | 'remove';

type FragmentUpdate = { target: string; action: FragmentAction; html: string };

/**
 * Aplica un fragmento al DOM.
 *
 * IMPORTANTE: el selector se resuelve ACÁ, en el momento de aplicar, no se cachea el
 * nodo. Con View Transitions el DOM se intercambia entre navegaciones, y un nodo
 * cacheado quedaría desprendido. Resolviendo en el momento, esto sobrevive cualquier
 * navegación sin re-bindear nada.
 */
export function applyFragment({ target, action, html }: FragmentUpdate): void {
  const el = document.querySelector(target);
  if (!el) return;

  if (action === 'remove') {
    el.remove();
    return;
  }

  const frag = document.createRange().createContextualFragment(html);

  switch (action) {
    case 'replace': el.replaceWith(frag); break;
    case 'update':  el.replaceChildren(frag); break;
    case 'append':  el.append(frag); break;
    case 'prepend': el.prepend(frag); break;
    case 'before':  el.before(frag); break;
    case 'after':   el.after(frag); break;
  }
}

/**
 * Conecta el canal SSE.
 *
 * Solo trae lo que el usuario NO provocó: cambios de otro operador, jobs que terminan,
 * alertas. El resultado de la propia acción del usuario vuelve en la respuesta del
 * Action — rutearlo por SSE serían tres hops donde alcanza uno, y mete una carrera.
 *
 * El navegador reconecta solo. Al reconectar, lo más simple y suficiente es que la
 * página refetchee su estado; implementar replay con Last-Event-ID solo si aparece una
 * razón concreta.
 *
 * Este módulo se ejecuta UNA vez: con View Transitions los scripts no se re-ejecutan
 * en cada navegación, así que el EventSource sobrevive y no se reconstruye.
 */
export function connectEvents(url = '/events'): EventSource {
  const es = new EventSource(url);

  es.onmessage = (event) => {
    try {
      applyFragment(JSON.parse(event.data) as FragmentUpdate);
    } catch (err) {
      console.error('fragmento SSE inválido', err);
    }
  };

  es.onerror = () => {
    // No cerrar: EventSource reintenta solo con backoff.
    console.warn('SSE desconectado, reintentando');
  };

  return es;
}
