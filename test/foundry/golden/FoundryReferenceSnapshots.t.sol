// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import { Test } from "forge-std/Test.sol";
import { SqrtPriceMath } from "@uniswap/v4-core/src/libraries/SqrtPriceMath.sol";
import { SwapMath } from "@uniswap/v4-core/src/libraries/SwapMath.sol";
import { TickMath } from "@uniswap/v4-core/src/libraries/TickMath.sol";

import { WAD, PEEL_BOUNTY_PIPS } from "contracts/libraries/ae/Constants.sol";
import { LUnitMath } from "contracts/libraries/ae/math/LUnitMath.sol";
import { SqrtMath } from "contracts/libraries/ae/math/SqrtMath.sol";
import { LiquidationMath } from "contracts/libraries/ae/keeper/LiquidationMath.sol";

contract FoundryReferenceSnapshotsTest is Test {
  uint160 private constant Q96 = 79228162514264337593543950336;
  uint256 private constant Q128 = 1 << 128;
  string private constant UNISWAP_PATH = "reports/golden/foundry-uniswap-v4-reference.json";
  string private constant AEGIS_PATH = "reports/golden/foundry-aegis-vault-reference.json";

  function test_WriteUniswapV4ReferenceSnapshot() public {
    vm.writeFile(UNISWAP_PATH, "");
    vm.writeLine(UNISWAP_PATH, "{");
    vm.writeLine(UNISWAP_PATH, '  "fixture_version": "aegis-vault-challenge-v1-foundry-snapshot",');
    vm.writeLine(UNISWAP_PATH, '  "source": "foundry v4-core reference libraries",');
    vm.writeLine(UNISWAP_PATH, '  "values": {');
    _writeUniswapTickValues();
    _writeUniswapSwap0Values();
    _writeUniswapSwap1Values();
    _writeUniswapCrossingAndFeeValues();
    vm.writeLine(UNISWAP_PATH, "  }");
    vm.writeLine(UNISWAP_PATH, "}");
  }

  function test_WriteAegisReferenceSnapshot() public {
    vm.writeFile(AEGIS_PATH, "");
    vm.writeLine(AEGIS_PATH, "{");
    vm.writeLine(AEGIS_PATH, '  "fixture_version": "aegis-vault-challenge-v1-foundry-snapshot",');
    vm.writeLine(AEGIS_PATH, '  "source": "foundry AEGIS LUnit/SqrtMath reference libraries",');
    vm.writeLine(AEGIS_PATH, '  "values": {');
    _writeAegisFullRangeAndBorrow();
    _writeAegisRepayAndRisk();
    _writeAegisInterest();
    _writeAegisDebtMark();
    _writeAegisHookFeeMath();
    _writeAegisLimitOrderShape();
    _writeAegisRepairMath();
    vm.writeLine(AEGIS_PATH, "  }");
    vm.writeLine(AEGIS_PATH, "}");
  }

  function _writeUniswapTickValues() private {
    _line(UNISWAP_PATH, "tick_min_sqrt_price_x96", vm.toString(uint256(TickMath.getSqrtPriceAtTick(-887272))), true);
    _line(UNISWAP_PATH, "tick_zero_sqrt_price_x96", vm.toString(uint256(TickMath.getSqrtPriceAtTick(0))), true);
    _line(UNISWAP_PATH, "tick_max_sqrt_price_x96", vm.toString(uint256(TickMath.getSqrtPriceAtTick(887272))), true);
  }

  function _writeUniswapSwap0Values() private {
    (uint160 sqrtAfter, uint256 amountIn, uint256 amountOut, uint256 feeAmount) =
      SwapMath.computeSwapStep(Q96, TickMath.getSqrtPriceAtTick(-120), 1_000_000, -1000, 0);
    _line(UNISWAP_PATH, "swap0_sqrt_price_x96_after", vm.toString(uint256(sqrtAfter)), true);
    _line(UNISWAP_PATH, "swap0_amount0_in", vm.toString(amountIn), true);
    _line(UNISWAP_PATH, "swap0_amount1_out", vm.toString(amountOut), true);
    _line(UNISWAP_PATH, "swap0_fee_amount", vm.toString(feeAmount), true);
    _line(UNISWAP_PATH, "swap0_final_tick", vm.toString(TickMath.getTickAtSqrtPrice(sqrtAfter)), true);
  }

  function _writeUniswapSwap1Values() private {
    (uint160 sqrtAfter, uint256 amountIn, uint256 amountOut, uint256 feeAmount) =
      SwapMath.computeSwapStep(Q96, TickMath.getSqrtPriceAtTick(120), 1_000_000, -1000, 0);
    _line(UNISWAP_PATH, "swap1_sqrt_price_x96_after", vm.toString(uint256(sqrtAfter)), true);
    _line(UNISWAP_PATH, "swap1_amount1_in", vm.toString(amountIn), true);
    _line(UNISWAP_PATH, "swap1_amount0_out", vm.toString(amountOut), true);
    _line(UNISWAP_PATH, "swap1_fee_amount", vm.toString(feeAmount), true);
    _line(UNISWAP_PATH, "swap1_final_tick", vm.toString(TickMath.getTickAtSqrtPrice(sqrtAfter)), true);
  }

  function _writeUniswapCrossingAndFeeValues() private {
    uint256 amount1ToUpperTick = SqrtPriceMath.getAmount1Delta(Q96, TickMath.getSqrtPriceAtTick(60), 1_000_000, true);
    uint256 amount0ToLowerTick = SqrtPriceMath.getAmount0Delta(TickMath.getSqrtPriceAtTick(-60), Q96, 1_000_000, true);
    uint256 feeGrowthForThirtyToken0 = 30 * Q128 / 1_000_000;
    _line(UNISWAP_PATH, "tick_up_amount_in_consumed", vm.toString(amount1ToUpperTick), true);
    _line(UNISWAP_PATH, "tick_down_amount_in_consumed", vm.toString(amount0ToLowerTick), true);
    _line(UNISWAP_PATH, "fee_growth_global0_delta_x128", vm.toString(feeGrowthForThirtyToken0), false);
  }

  function _writeAegisFullRangeAndBorrow() private {
    (int24 minTick, int24 maxTick) = LUnitMath.getActualFullRangeTicks(60);
    (uint160 minSqrtPriceX96, uint160 maxSqrtPriceX96) = LUnitMath.getActualFullRangePrices(60);
    uint128 borrowLiquidity = LUnitMath.liquidityForPrincipal(1000, WAD);
    _line(AEGIS_PATH, "full_range_min_tick", vm.toString(minTick), true);
    _line(AEGIS_PATH, "full_range_max_tick", vm.toString(maxTick), true);
    _line(AEGIS_PATH, "borrow_liquidity_removed", vm.toString(uint256(borrowLiquidity)), true);
    _line(AEGIS_PATH, "borrow_idle0_delta", vm.toString(SqrtPriceMath.getAmount0Delta(Q96, maxSqrtPriceX96, borrowLiquidity, true)), true);
    _line(AEGIS_PATH, "borrow_idle1_delta", vm.toString(SqrtPriceMath.getAmount1Delta(minSqrtPriceX96, Q96, borrowLiquidity, true)), true);
  }

  function _writeAegisRepayAndRisk() private {
    uint128 repayLiquidity = LUnitMath.liquidityForPrincipal(500, 1_050_000_000_000_000_000);
    uint128 actualRepaid = LUnitMath.principalFromLiquidity(repayLiquidity, 1_050_000_000_000_000_000);
    uint256 collateralFloorL = SqrtMath.sqrtProductLowerBound(100, 400);
    uint256 ltvPips = 100 * WAD * 1_000_000 / (collateralFloorL * WAD);
    _line(AEGIS_PATH, "repay_target_liquidity", vm.toString(uint256(repayLiquidity)), true);
    _line(AEGIS_PATH, "repay_geometric_mean", vm.toString(uint256(repayLiquidity)), true);
    _line(AEGIS_PATH, "repay_actual_repaid_l", vm.toString(uint256(actualRepaid)), true);
    _line(AEGIS_PATH, "ltv_idle_collateral_floor_l", vm.toString(collateralFloorL), true);
    _line(AEGIS_PATH, "ltv_idle_ltv_pips", vm.toString(ltvPips), true);
    _line(AEGIS_PATH, "ltv_one_sided_collateral_floor_l", "0", true);
    _line(AEGIS_PATH, "ltv_one_sided_ltv_pips", "1000000", true);
    _line(AEGIS_PATH, "lock_reject_ltv_pips", "901000", true);
  }

  function _writeAegisInterest() private {
    uint256 borrowIndexDelta = WAD * 1_000_000_000 * 60 / WAD;
    _line(AEGIS_PATH, "interest_delta_borrow_index_wad", vm.toString(borrowIndexDelta), true);
    _line(AEGIS_PATH, "interest_borrow_index_wad_after", vm.toString(WAD + borrowIndexDelta), true);
    _line(AEGIS_PATH, "interest_accrued_wad", vm.toString(100_000 * borrowIndexDelta), true);
  }

  function _writeAegisDebtMark() private {
    (, uint160 maxSqrtPriceX96) = LUnitMath.getActualFullRangePrices(60);
    (uint160 minSqrtPriceX96,) = LUnitMath.getActualFullRangePrices(60);
    uint128 targetLiquidity = LUnitMath.liquidityForPrincipal(1000, 1_050_000_000_000_000_000);
    uint256 liability0 = SqrtPriceMath.getAmount0Delta(Q96, maxSqrtPriceX96, targetLiquidity, true);
    uint256 liability1 = SqrtPriceMath.getAmount1Delta(minSqrtPriceX96, Q96, targetLiquidity, true);
    uint256 geometricMean = SqrtMath.sqrtProductLowerBound(liability0, liability1);
    uint128 repaid = LUnitMath.principalFromLiquidity(geometricMean, 1_050_000_000_000_000_000);
    _line(AEGIS_PATH, "debt_mark_target_liquidity", vm.toString(uint256(targetLiquidity)), true);
    _line(AEGIS_PATH, "debt_mark_liability0", vm.toString(liability0), true);
    _line(AEGIS_PATH, "debt_mark_liability1", vm.toString(liability1), true);
    _line(AEGIS_PATH, "debt_mark_geometric_mean", vm.toString(geometricMean), true);
    _line(AEGIS_PATH, "debt_mark_repaid_l", vm.toString(uint256(repaid)), true);
    _line(AEGIS_PATH, "debt_repayment_value", vm.toString(liability0 + liability1), true);
  }

  function _writeAegisRepairMath() private {
    (bool zeroForOne, uint256 exactOut) = LiquidationMath.computeMicroLiqSwapDeficit(10_000_000, 100_000, 133_196, 133_196);
    _line(AEGIS_PATH, "repair_repay_fraction_pips", vm.toString(LiquidationMath.repayFractionPips(994_000, 993_000, 996_000)), true);
    _line(AEGIS_PATH, "repair_keeper_fee_pips", vm.toString(LiquidationMath.keeperFeePips(994_000, 993_000, 996_000)), true);
    _line(AEGIS_PATH, "peel_bounty_pips", vm.toString(uint256(PEEL_BOUNTY_PIPS)), true);
    _line(AEGIS_PATH, "repair_swap_deficit_zero_for_one", zeroForOne ? "true" : "false", true);
    _line(AEGIS_PATH, "repair_swap_deficit_exact_out", vm.toString(exactOut), false);
  }

  function _writeAegisHookFeeMath() private {
    _line(AEGIS_PATH, "hook_fee_exact_in_10000_fee4000_cut1000", vm.toString(_hookFeeFromInput(10_000, 4000, 1000)), true);
    _line(AEGIS_PATH, "hook_fee_exact_in_10000_fee4000_cut500000", vm.toString(_hookFeeFromInput(10_000, 4000, 500_000)), true);
    _line(AEGIS_PATH, "hook_reinvest_min_liquidity", "1000", true);
  }

  function _writeAegisLimitOrderShape() private {
    _line(AEGIS_PATH, "limit_order_tick_lower", "60", true);
    _line(AEGIS_PATH, "limit_order_tick_upper_for_spacing60", "120", true);
    _line(AEGIS_PATH, "limit_order_lower_liquidity_net", "1000", true);
    _line(AEGIS_PATH, "limit_order_upper_liquidity_net", "-1000", true);
    _line(
      AEGIS_PATH,
      "limit_order_amount0_for_liquidity1000_tick60_120",
      vm.toString(SqrtPriceMath.getAmount0Delta(TickMath.getSqrtPriceAtTick(60), TickMath.getSqrtPriceAtTick(120), 1000, true)),
      true
    );
    _line(
      AEGIS_PATH,
      "limit_order_amount0_for_liquidity2000_tick60_120",
      vm.toString(SqrtPriceMath.getAmount0Delta(TickMath.getSqrtPriceAtTick(60), TickMath.getSqrtPriceAtTick(120), 2000, true)),
      true
    );
    _line(
      AEGIS_PATH,
      "limit_order_amount1_for_liquidity3000_tick60_120",
      vm.toString(SqrtPriceMath.getAmount1Delta(TickMath.getSqrtPriceAtTick(60), TickMath.getSqrtPriceAtTick(120), 3000, true)),
      true
    );
  }

  function _hookFeeFromInput(uint256 amountIn, uint256 dynamicFeePips, uint256 hookFeePpm) private pure returns (uint256) {
    uint256 swapFeeAmount = amountIn * dynamicFeePips / 1_000_000;
    if (swapFeeAmount == 0 || hookFeePpm == 0) {
      return 0;
    }
    return (swapFeeAmount * hookFeePpm + 1_000_000 - 1) / 1_000_000;
  }

  function _line(string memory path, string memory key, string memory value, bool comma) private {
    vm.writeLine(path, string.concat('    "', key, '": "', value, '"', comma ? "," : ""));
  }
}
