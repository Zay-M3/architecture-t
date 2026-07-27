/**
 * Renderizado de fragmentos y contrato de intercambio.
 *
 * El MISMO shape se usa venga por respuesta de un Action o por SSE. Eso es lo
 * importante de fijar desde el día uno: el transporte es intercambiable, el contrato
 * no. El vocabulario es el de Turbo Streams (Hotwire) a propósito — ya está probado.
 *
 * Ver 05-transformador-y-frontend.md.
 */

import { experimental_AstroContainer } from 'astro/container';
import type { AstroComponentFactory } from 'astro/runtime/server/index.js';

export type FragmentAction =
  | 'replace'   // reemplaza el elemento entero
  | 'update'    // reemplaza los hijos, conserva el elemento
  | 'append'
  | 'prepend'
  | 'before'
  | 'after'
  | 'remove';

export type FragmentUpdate = {
  /** Selector CSS del destino, ej. "#oc-123-lines" */
  target: string;
  action: FragmentAction;
  html: string;
};

// El container es caro de crear: uno por proceso.
//
// Caveat: el prefijo `experimental_` está en el nombre de la API. Puede cambiar entre
// versiones MENORES de Astro, y cada fragmento pasa por acá. Pinear la versión de Astro
// y leer el changelog en cada bump.
let containerPromise: Promise<Awaited<ReturnType<typeof experimental_AstroContainer.create>>> | null = null;

function getContainer() {
  containerPromise ??= experimental_AstroContainer.create();
  return containerPromise;
}

/**
 * Renderiza un componente .astro a HTML suelto, fuera de un request de página.
 *
 * `partial: true` es lo que evita que salga envuelto en el shell del documento
 * (<html>, <head>, etc.) — para un fragmento eso sería basura.
 */
export async function renderFragment(
  target: string,
  action: FragmentAction,
  Component: AstroComponentFactory,
  props: Record<string, unknown> = {},
): Promise<FragmentUpdate> {
  const container = await getContainer();
  const html = await container.renderToString(Component, { props, partial: true });
  return { target, action, html };
}

/** Para `remove`, que no necesita renderizar nada. */
export function removeFragment(target: string): FragmentUpdate {
  return { target, action: 'remove', html: '' };
}
