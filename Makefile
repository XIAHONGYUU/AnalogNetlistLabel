.PHONY: test demo analyze clean

.RECIPEPREFIX = >

test:
> python3 -m unittest discover -s tests -v

demo:
> ./scripts/demo.sh

analyze:
> python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out out/generic_ota

clean:
> rm -rf out review __pycache__ netlistlabel/__pycache__ tests/__pycache__
