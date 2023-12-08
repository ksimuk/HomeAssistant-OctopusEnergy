import logging
from datetime import datetime, timedelta

from . import BaseCoordinatorResult, async_check_valid_tariff
from ..utils import get_active_tariff_code

from homeassistant.util.dt import (now)
from homeassistant.helpers.update_coordinator import (
  DataUpdateCoordinator
)

from homeassistant.helpers import issue_registry as ir

from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  DOMAIN,

  DATA_CLIENT,
  DATA_ACCOUNT,
  DATA_ACCOUNT_COORDINATOR,
  REFRESH_RATE_IN_MINUTES_ACCOUNT,
)

from ..api_client import OctopusEnergyApiClient

_LOGGER = logging.getLogger(__name__)

class AccountCoordinatorResult(BaseCoordinatorResult):
  account: dict

  def __init__(self, last_retrieved: datetime, request_attempts: int, account: dict):
    super().__init__(last_retrieved, request_attempts, REFRESH_RATE_IN_MINUTES_ACCOUNT)
    self.account = account

async def async_refresh_account(
  hass,
  current: datetime,
  client: OctopusEnergyApiClient,
  account_id: str,
  previous_request: AccountCoordinatorResult
):
  if (current >= previous_request.next_refresh):
    account_info = None
    try:
      account_info = await client.async_get_account(account_id)

      if account_info is None:
        ir.async_create_issue(
          hass,
          DOMAIN,
          f"account_not_found_{account_id}",
          is_fixable=False,
          severity=ir.IssueSeverity.ERROR,
          learn_more_url="https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy/blob/develop/_docs/repairs/account_not_found.md",
          translation_key="account_not_found",
          translation_placeholders={ "account_id": account_id },
        )
      else:
        _LOGGER.debug('Account information retrieved')

        ir.async_delete_issue(hass, DOMAIN, f"account_not_found_{account_id}")

        if account_info is not None and len(account_info["electricity_meter_points"]) > 0:
          for point in account_info["electricity_meter_points"]:
            active_tariff_code = get_active_tariff_code(current, point["agreements"])
            await async_check_valid_tariff(hass, client, active_tariff_code, True)

        if account_info is not None and len(account_info["gas_meter_points"]) > 0:
          for point in account_info["gas_meter_points"]:
            active_tariff_code = get_active_tariff_code(current, point["agreements"])
            await async_check_valid_tariff(hass, client, active_tariff_code, False)

        return AccountCoordinatorResult(current, 1, account_info)
    except:
      # count exceptions as failure to retrieve account
      _LOGGER.debug('Failed to retrieve account information')

      return AccountCoordinatorResult(
        previous_request.last_retrieved,
        previous_request.request_attempts + 1,
        previous_request.account
      )

  return previous_request

async def async_setup_account_info_coordinator(hass, account_id: str):
  async def async_update_account_data():
    """Fetch data from API endpoint."""
    # Only get data every half hour or if we don't have any data
    current = now()
    client: OctopusEnergyApiClient = hass.data[DOMAIN][DATA_CLIENT]

    if DATA_ACCOUNT not in hass.data[DOMAIN] or hass.data[DOMAIN][DATA_ACCOUNT] is None:
      raise Exception("Failed to find account information")

    hass.data[DOMAIN][DATA_ACCOUNT] = await async_refresh_account(
      hass,
      current,
      client,
      account_id,
      hass.data[DOMAIN][DATA_ACCOUNT]
    )
    
    return hass.data[DOMAIN][DATA_ACCOUNT]

  hass.data[DOMAIN][DATA_ACCOUNT_COORDINATOR] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name="update_account",
    update_method=async_update_account_data,
    # Because of how we're using the data, we'll update every minute, but we will only actually retrieve
    # data every 30 minutes
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True
  )
  
  await hass.data[DOMAIN][DATA_ACCOUNT_COORDINATOR].async_config_entry_first_refresh()