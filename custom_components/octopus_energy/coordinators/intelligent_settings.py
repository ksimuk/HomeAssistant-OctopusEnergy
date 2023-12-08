import logging
from datetime import datetime, timedelta

from homeassistant.util.dt import (utcnow)
from homeassistant.helpers.update_coordinator import (
  DataUpdateCoordinator
)
from homeassistant.helpers import storage

from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  DOMAIN,

  DATA_CLIENT,
  DATA_ACCOUNT,
  DATA_ACCOUNT_COORDINATOR,
  DATA_INTELLIGENT_SETTINGS,
  DATA_INTELLIGENT_SETTINGS_COORDINATOR,
  REFRESH_RATE_IN_MINUTES_INTELLIGENT,
)

from ..api_client import OctopusEnergyApiClient
from ..api_client.intelligent_settings import IntelligentSettings
from . import BaseCoordinatorResult

from ..intelligent import async_mock_intelligent_data, has_intelligent_tariff, mock_intelligent_settings

_LOGGER = logging.getLogger(__name__)

class IntelligentCoordinatorResult(BaseCoordinatorResult):
  settings: IntelligentSettings

  def __init__(self, last_retrieved: datetime, request_attempts: int, settings: IntelligentSettings):
    super().__init__(last_retrieved, request_attempts, REFRESH_RATE_IN_MINUTES_INTELLIGENT)
    self.settings = settings

async def async_refresh_intelligent_settings(
  current: datetime,
  client: OctopusEnergyApiClient,
  account_info,
  existing_intelligent_settings_result: IntelligentCoordinatorResult,
  is_settings_mocked: bool
):
  if (account_info is not None):
    account_id = account_info["id"]
    if (existing_intelligent_settings_result is None or current >= existing_intelligent_settings_result.next_refresh):
      settings = None
      if has_intelligent_tariff(current, account_info):
        try:
          settings = await client.async_get_intelligent_settings(account_id)
          _LOGGER.debug(f'Intelligent settings retrieved for account {account_id}')
        except:
          _LOGGER.debug('Failed to retrieve intelligent settings for account {account_id}')

      if is_settings_mocked:
        settings = mock_intelligent_settings()

      if settings is not None:
        return IntelligentCoordinatorResult(current, 1, settings)
      elif (existing_intelligent_settings_result is not None):
        _LOGGER.debug(f"Failed to retrieve new intelligent settings, so using cached settings")
        return IntelligentCoordinatorResult(
          existing_intelligent_settings_result.last_retrieved,
          existing_intelligent_settings_result.request_attempts + 1,
          existing_intelligent_settings_result.settings
        )
      else:
        # We want to force into our fallback mode
        return IntelligentCoordinatorResult(current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_INTELLIGENT), 2, None)
  
  return existing_intelligent_settings_result
  
async def async_setup_intelligent_settings_coordinator(hass):
  # Reset data rates as we might have new information
  hass.data[DOMAIN][DATA_INTELLIGENT_SETTINGS] = None
  
  async def async_update_intelligent_settings_data():
    """Fetch data from API endpoint."""
    # Request our account data to be refreshed
    account_coordinator = hass.data[DOMAIN][DATA_ACCOUNT_COORDINATOR]
    if account_coordinator is not None:
      await account_coordinator.async_request_refresh()

    current = utcnow()
    client: OctopusEnergyApiClient = hass.data[DOMAIN][DATA_CLIENT]
    account_result = hass.data[DOMAIN][DATA_ACCOUNT]
    account_info = account_result.account if account_result is not None else None
      
    hass.data[DOMAIN][DATA_INTELLIGENT_SETTINGS] = await async_refresh_intelligent_settings(
      current,
      client,
      account_info,
      hass.data[DOMAIN][DATA_INTELLIGENT_SETTINGS] if DATA_INTELLIGENT_SETTINGS in hass.data[DOMAIN] else None,
      await async_mock_intelligent_data(hass)
    )

    return hass.data[DOMAIN][DATA_INTELLIGENT_SETTINGS]

  hass.data[DOMAIN][DATA_INTELLIGENT_SETTINGS_COORDINATOR] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name="intelligent_settings",
    update_method=async_update_intelligent_settings_data,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True
  )

  await hass.data[DOMAIN][DATA_INTELLIGENT_SETTINGS_COORDINATOR].async_config_entry_first_refresh()