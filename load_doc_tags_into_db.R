source("../apps/scripts/common.R")
source("../apps/scripts/db.R")
shelf(
  dplyr, jsonlite, purrr, tibble, tidyr)

lst <- read_json("docs_excerpts_tags.json")
# glimpse(lst)
# convert list_json1 to a tibble
# d <- as_tibble(lst, validate = F)

d <- tibble(
  ba_doc_file = map_chr(lst, 'file_name'),
  excerpt     = map_chr(lst, 'text_excerpt'),
  tag_sql     = map(lst, 'tags')) |>
  rowid_to_column("id_seq") |>
  arrange(ba_doc_file, id_seq) |>
  rowid_to_column("rowid") |>
  select(-id_seq)

# dbExecute(con, "DELETE FROM ba_doc_excerpts")
d_excerpts <- d |>
  select(rowid, ba_doc_file, excerpt)
dbAppendTable(con, "ba_doc_excerpts", d_excerpts)
# tbl(con, "ba_doc_excerpts")

v_tags <- tbl(con, "tags") |>
  pull(tag_sql) |>
  as.character() |>
  setdiff(
    c("Management.NoneIdentified"))
d_tags <- d |>
  select(rowid, tag_sql) |>
  mutate(
    tag_sql = map(tag_sql, unlist)) |>
  unnest(tag_sql) |>
  filter(
    tag_sql %in% v_tags)
# setdiff(d_tags$tag_sql, v_tags)

# dbExecute(con, "DELETE FROM ba_doc_excerpt_tags")
# TODO: rowid SERIAL to auto increment in db
dbAppendTable(con, "ba_doc_excerpt_tags", d_tags)
# tbl(con, "ba_doc_excerpt_tags")
