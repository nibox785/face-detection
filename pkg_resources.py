from importlib import import_module, resources


def resource_stream(package_or_requirement, resource_name):
    package = import_module(package_or_requirement)
    return resources.files(package).joinpath(resource_name).open('rb')


def resource_filename(package_or_requirement, resource_name):
    package = import_module(package_or_requirement)
    return str(resources.files(package).joinpath(resource_name))


def get_distribution(_name):
    class _Distribution:
        version = '0.0.0'

    return _Distribution()
