from uuid import UUID
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.middleware.rate_limit import rate_limit
from app.services import wallet_transfers as service

wallet_transfers_bp = Blueprint('wallet_transfers', __name__)


@wallet_transfers_bp.route('', methods=['GET', 'POST'])
@require_auth
@rate_limit(max_requests=30, window_seconds=60)
def transfers():
    try:
        if request.method == 'GET':
            return jsonify(service.rpc('limits', g.user_id))
        return jsonify({'transfer': service.send(g.user_id, request.get_json(silent=True))})
    except service.TransferError as exc:
        return jsonify({'error': str(exc), 'code': exc.code}), exc.status
    except Exception:
        # A lost response can follow a committed transfer. Never say nothing
        # moved unless an authoritative validation error proves that outcome.
        return jsonify({'error': 'Transfer status could not be confirmed. Check this transfer before sending again.', 'code': 'transfer_uncertain'}), 503


@wallet_transfers_bp.route('/recipient', methods=['GET'])
@require_auth
@rate_limit(max_requests=20, window_seconds=60)
def recipient():
    try:
        return jsonify({'recipient': service.rpc('lookup', g.user_id, data=service.recipient_lookup(request.args))})
    except service.TransferError as exc:
        return jsonify({'error': str(exc), 'code': exc.code}), exc.status
    except Exception:
        return jsonify({'error': 'Recipient lookup is unavailable. Please try again.'}), 503


@wallet_transfers_bp.route('/<transfer_id>', methods=['GET'])
@require_auth
@rate_limit(max_requests=30, window_seconds=60)
def receipt(transfer_id):
    try:
        transfer_id = str(UUID(transfer_id))
        return jsonify({'transfer': service.rpc('get', g.user_id, transfer_id)})
    except service.TransferError as exc:
        return jsonify({'error': str(exc), 'code': exc.code}), exc.status
    except ValueError:
        return jsonify({'error': 'Invalid transfer reference.', 'code': 'invalid_transfer'}), 400
    except Exception:
        return jsonify({'error': 'The receipt could not be loaded. Check again before sending another transfer.'}), 503
