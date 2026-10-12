# Model

`from fb2kit import ...` (or `from fb2kit.model import ...`). All nodes are `@dataclass(frozen=True, slots=True)`: immutable,
hashable, compared by content. A modified copy is made with `dataclasses.replace(node, ...)`.

## Metadata

::: fb2kit.model.Description

::: fb2kit.model.TitleInfo

::: fb2kit.model.DocumentInfo

::: fb2kit.model.PublishInfo

::: fb2kit.model.CustomInfo

::: fb2kit.model.Author

::: fb2kit.model.Sequence

::: fb2kit.model.Date

## Structure

::: fb2kit.model.Body

::: fb2kit.model.Section

::: fb2kit.model.Title

::: fb2kit.model.Epigraph

::: fb2kit.model.Annotation

## Blocks

::: fb2kit.model.Paragraph

::: fb2kit.model.Subtitle

::: fb2kit.model.EmptyLine

::: fb2kit.model.TextAuthor

::: fb2kit.model.Cite

::: fb2kit.model.Poem

::: fb2kit.model.Stanza

::: fb2kit.model.Verse

::: fb2kit.model.Table

::: fb2kit.model.Row

::: fb2kit.model.Cell

## Inline nodes

::: fb2kit.model.Text

::: fb2kit.model.Style

::: fb2kit.model.Link

::: fb2kit.model.Image

::: fb2kit.model.Raw

## Attachments

::: fb2kit.model.Binary

## Utilities

::: fb2kit.model.iter_nodes

::: fb2kit.model.decode_b64

## Type unions

| Name | Members |
|---|---|
| `Inline` | `Text | Style | Link | Image | Raw` |
| `Block` | `Paragraph | Subtitle | EmptyLine | Title | Epigraph | Annotation | Poem | Cite | TextAuthor | Table | Image | Raw` |
| `Node` | `Inline | Block | Section | Body | Stanza | Verse | Row | Cell` |
