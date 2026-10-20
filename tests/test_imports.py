def test_runtime_dependencies_import_without_client_calls() -> None:
    import av
    import dotenv
    import PIL
    import openrouter
    from openrouter import OpenRouter

    assert av.__name__ == "av"
    assert PIL.__name__ == "PIL"
    assert callable(dotenv.load_dotenv)
    assert callable(OpenRouter)
