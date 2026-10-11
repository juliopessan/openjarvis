from openjarvis.speech.sentences import split_sentences


def test_splits_at_sentence_ends() -> None:
    text = "Abri o Safari para você agora. A previsão é de sol amanhã na cidade!"
    assert split_sentences(text) == [
        "Abri o Safari para você agora.",
        "A previsão é de sol amanhã na cidade!",
    ]


def test_short_fragments_are_merged_into_a_neighbour() -> None:
    parts = split_sentences("Ok. Já abri o aplicativo que você pediu agora.")
    assert parts == ["Ok. Já abri o aplicativo que você pediu agora."]


def test_trailing_fragment_joins_the_previous_sentence() -> None:
    parts = split_sentences("Abri o navegador com a página que você queria. Pronto.")
    assert parts == ["Abri o navegador com a página que você queria. Pronto."]


def test_decimals_and_abbreviations_do_not_split() -> None:
    assert split_sentences("A temperatura é 21.5 graus hoje por aqui.") == [
        "A temperatura é 21.5 graus hoje por aqui."
    ]


def test_blank_text_gives_no_sentences() -> None:
    assert split_sentences("   \n ") == []
