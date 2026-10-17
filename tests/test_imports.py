def test_runtime_dependencies_import_without_client_calls() -> None:
    import dotenv
    import PIL
    import openrouter
    from openrouter import OpenRouter

    assert PIL.__name__ == "PIL"
    assert callable(dotenv.load_dotenv)
    assert callable(OpenRouter)
