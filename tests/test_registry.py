from bioreport.registry import Module, Registry, get_registry


def test_builtin_rna_modules_are_namespaced_and_resolvable():
    registry = get_registry()
    assert "rna.qc.fastp" in registry.modules
    assert registry.resolve("rna.results.deg").category == "results"


def test_registry_rejects_cross_namespace_module_ids():
    registry = Registry()
    try:
        registry.register_omics("atac", [Module("rna.bad", "x.qmd", "bad")])
    except ValueError as error:
        assert "outside namespace" in str(error)
    else:
        raise AssertionError("cross-namespace module was accepted")


def test_registry_requires_core_inputs_but_tolerates_missing_qc_inputs():
    registry = get_registry()
    assert registry.validate_inputs(['rna.qc', 'rna.qc.screen'], set()) == []
    assert registry.validate_inputs(['rna.results.matrix'], set()) == ['tpm_file']


def test_registry_supports_omics_aliases_and_defaults_without_core_changes():
    registry = Registry()
    registry.register_omics(
        "foo",
        [Module("foo.index", "qmd/index.qmd", "Index", category="index")],
        aliases={"index": "foo.index"},
        defaults=("foo.index",),
    )

    assert registry.canonical("index") == "foo.index"
    assert registry.default_modules == ("foo.index",)
