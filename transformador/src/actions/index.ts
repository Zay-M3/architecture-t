/**
 * Astro Actions: el canal navegador -> servidor.
 *
 * Con un <form> no envían JavaScript y funcionan incluso sin JS habilitado. Para las
 * transiciones de estado (aprobar, enviar, cerrar, cancelar) esto es MEJOR que un
 * componente de framework: el motivo lo valida el dominio y el error vuelve en el
 * re-render, sin estados de loading ni fetch a mano.
 *
 * El Action devuelve el fragmento YA RENDERIZADO. El resultado de la propia acción del
 * usuario no pasa por SSE — sería un hop de más y una carrera.
 */

import { defineAction } from 'astro:actions';
import { z } from 'astro:schema';

import { ejemplo } from '../lib/grpc';
import { toActionError } from '../lib/errors';
import { renderFragment } from '../lib/fragments';
// import EjemploHeader from '../components/EjemploHeader.astro';

export const server = {
  /**
   * Transición borrador -> confirmado.
   *
   * El motivo se valida en el DOMINIO (>= 10 palabras), no acá: si la regla viviera en
   * el transformador, existiría dos veces y divergiría. Acá solo se traduce el error.
   */
  confirmarEjemplo: defineAction({
    accept: 'form',
    input: z.object({
      id: z.string().min(1),
      motivo: z.string().min(1),
    }),
    handler: async ({ id, motivo }, ctx) => {
      try {
        const actualizado = await ejemplo.confirmarEjemplo({
          id,
          motivo,
          actorUserId: (ctx.locals as any).userId ?? 0,
          actorUserName: (ctx.locals as any).userName ?? 'desconocido',
        });

        // Devolver el fragmento renderizado, no JSON: si devolviera JSON, el cliente
        // tendría que renderizarlo, y eso exigiría plantillas en el navegador.
        // return await renderFragment('#ejemplo-header', 'replace', EjemploHeader, {
        //   ejemplo: actualizado,
        // });
        return actualizado;
      } catch (err) {
        throw toActionError(err);
      }
    },
  }),
};
