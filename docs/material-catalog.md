# Materials and colours

[← back to the README](../README.md)

The printer owner manages the choices shown on the request form at
`/admin/catalog`. A material is offered only when it is turned on and has at
least one active colour. Arrows set the order in which materials and colours
appear.

Turning an entry off is temporary. Removing it deletes the catalogue row; when
a material is removed, its colour rows go with it. Neither operation changes
an existing ticket because every request snapshots its material label, colour
label, representative hex, rendered swatch, and swatch mode when submitted.

## Swatch types

- **Solid** takes one colour.
- **Gradient** takes a start and end colour.
- **Whatever** takes no colour input. It renders as a rainbow with a question
  mark and keeps that behavior even if its display name is changed.

The mode is stored separately from the editable colour name. No particular
spelling has hidden behavior.

## Validation

The request form is only a convenience. At submission time the server looks up
the posted material and colour together and accepts them only when both rows
are still active and related. A stale or hand-written form therefore cannot
request a combination the owner no longer offers.

Printing an old request again goes through the same lookup, because it is a
new request: if the material or colour has been taken off the shelf since, the
re-queue is refused and says so, and the old ticket is left as it was.

`GET /api/catalog` returns the same list the form is drawn from, for clients of
the JSON API — see [the API](api.md).

## What "whatever" paints

A ticket carries two colours: `colorStyle`, the swatch as drawn, and
`colorHex`, one representative colour for the places that need exactly one —
the 3D viewer and the tallies on the audit page. For a "whatever" entry the
swatch is the rainbow and the representative colour is a neutral grey
(`#b6bcc2`), because the filament is by definition not chosen yet.

## Rolling back

`Story.material` used to be a Postgres enum and is now text. The enum type is
deliberately left in the database, unused: the previous image's client casts
every insert to it, and the deploy wizard rolls back to that image when a
deploy fails its health check. Without the type, a rolled-back deployment
renders every page and refuses every upload. It can be dropped once no
deployment can roll back past this release.

`npm run verify:catalog` drives the real admin forms and upload endpoint. It is
destructive and should only target a development database; the suite restores
the default catalogue before it exits.
