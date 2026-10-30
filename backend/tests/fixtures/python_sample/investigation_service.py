import os


class InvestigationService:
    def delete_investigation(self, id):
        repository.delete(id)
