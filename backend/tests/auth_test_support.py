from unittest.mock import MagicMock, patch
from app.main import app
from app.api.auth import require_user
from app.services.insforge import get_insforge

class AuthenticatedAPITest:
    """Existing API regression cases run with explicit fake authenticated dependencies."""
    def setUp(self):
        super().setUp()
        self.context_patch = patch('app.api.investigate.resolve_context', return_value={'context': 'test-context', 'cluster': 'test-cluster'})
        self.context_patch.start()
        self.addCleanup(self.context_patch.stop)
        self.saved_overrides = dict(app.dependency_overrides)
        self.fake_service = MagicMock()
        self.fake_service.records.return_value = [{}]
        app.dependency_overrides[require_user] = lambda: {'id': '11111111-1111-4111-8111-111111111111', 'email': 'test@example.com'}
        app.dependency_overrides[get_insforge] = lambda: self.fake_service

    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.saved_overrides)
        super().tearDown()
