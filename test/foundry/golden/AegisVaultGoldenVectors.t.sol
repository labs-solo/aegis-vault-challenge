// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import { Test } from "forge-std/Test.sol";
import { stdJson } from "forge-std/StdJson.sol";
import { SqrtPriceMath } from "@uniswap/v4-core/src/libraries/SqrtPriceMath.sol";
import { TickMath } from "@uniswap/v4-core/src/libraries/TickMath.sol";

import { WAD } from "contracts/libraries/ae/Constants.sol";
import { LUnitMath } from "contracts/libraries/ae/math/LUnitMath.sol";
import { SqrtMath } from "contracts/libraries/ae/math/SqrtMath.sol";

contract AegisVaultGoldenVectorsTest is Test {
  using stdJson for string;

  uint160 private constant Q96 = 79228162514264337593543950336;
  string private constant FIXTURE_PATH = "tests/golden/aegis_vault_vectors.json";

  function test_LUnitBorrowAndRepayFixtureMatchesReferenceMath() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".fixture_version"), "aegis-vault-challenge-v1");
    assertEq(json.readString(".vectors[0].id"), "AE-BORROW-001");
    assertEq(json.readString(".vectors[1].id"), "AE-REPAY-001");

    uint128 borrowLiquidity = LUnitMath.liquidityForPrincipal(1000, WAD);
    assertEq(uint256(borrowLiquidity), _readStringUint(json, ".vectors[0].expected.liquidity_removed"));

    uint128 repayLiquidity = LUnitMath.liquidityForPrincipal(500, 1_050_000_000_000_000_000);
    uint128 actualPrincipal = LUnitMath.principalFromLiquidity(repayLiquidity, 1_050_000_000_000_000_000);

    assertEq(uint256(repayLiquidity), _readStringUint(json, ".vectors[1].expected.target_liquidity"));
    assertEq(uint256(repayLiquidity), _readStringUint(json, ".vectors[1].expected.geometric_mean"));
    assertEq(uint256(actualPrincipal), _readStringUint(json, ".vectors[1].expected.actual_repaid_l"));
    assertEq(_readStringUint(json, ".vectors[1].expected.vault_rL_after"), 500);
  }

  function test_ActualFullRangeTicksAndAmountsMatchFixture() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    (int24 minTick, int24 maxTick) = LUnitMath.getActualFullRangeTicks(60);

    (uint160 minSqrtPriceX96, uint160 maxSqrtPriceX96) = LUnitMath.getActualFullRangePrices(60);
    uint256 amount0 = SqrtPriceMath.getAmount0Delta(Q96, maxSqrtPriceX96, 1000, true);
    uint256 amount1 = SqrtPriceMath.getAmount1Delta(minSqrtPriceX96, Q96, 1000, true);

    assertEq(minTick, int24(json.readInt(".vectors[11].input.full_range_min_tick")));
    assertEq(maxTick, int24(json.readInt(".vectors[11].input.full_range_max_tick")));
    assertEq(amount0, _readStringUint(json, ".vectors[0].expected.idle0_delta"));
    assertEq(amount1, _readStringUint(json, ".vectors[0].expected.idle1_delta"));
    assertEq(SqrtMath.sqrtProductLowerBound(amount0, amount1), _readStringUint(json, ".vectors[0].expected.liquidity_removed"));
  }

  function test_DebtMarkFixtureMatchesReferenceBridge() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".vectors[11].id"), "AE-DEBT-MARK-001");

    uint128 targetLiquidity = LUnitMath.liquidityForPrincipal(1000, 1_050_000_000_000_000_000);
    (uint160 minSqrtPriceX96, uint160 maxSqrtPriceX96) = LUnitMath.getActualFullRangePrices(60);
    uint256 liability0 = SqrtPriceMath.getAmount0Delta(Q96, maxSqrtPriceX96, targetLiquidity, true);
    uint256 liability1 = SqrtPriceMath.getAmount1Delta(minSqrtPriceX96, Q96, targetLiquidity, true);
    uint256 geometricMean = SqrtMath.sqrtProductLowerBound(liability0, liability1);
    uint128 repaid = LUnitMath.principalFromLiquidity(geometricMean, 1_050_000_000_000_000_000);

    assertEq(uint256(targetLiquidity), _readStringUint(json, ".vectors[11].expected.iterations[0].target_liquidity"));
    assertEq(liability0, _readStringUint(json, ".vectors[11].expected.liability0"));
    assertEq(liability1, _readStringUint(json, ".vectors[11].expected.liability1"));
    assertEq(geometricMean, _readStringUint(json, ".vectors[11].expected.iterations[0].geometric_mean"));
    assertEq(uint256(repaid), _readStringUint(json, ".vectors[11].expected.iterations[0].repaid_l"));
    assertEq(_readStringUint(json, ".vectors[11].expected.debt_repayment_value"), liability0 + liability1);
    assertEq(_readStringUint(json, ".vectors[11].expected.residual_l"), 0);
  }

  function test_LtvAndInterestFixturesMatchReferenceArithmetic() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".vectors[2].id"), "AE-LTV-001");
    assertEq(json.readString(".vectors[3].id"), "AE-LTV-002");
    assertEq(json.readString(".vectors[4].id"), "AE-LOCK-001");
    assertEq(json.readString(".vectors[5].id"), "AE-INTEREST-001");

    uint256 debtLWad = 100 * WAD;
    uint256 collateralFloorL = SqrtMath.sqrtProductLowerBound(100, 400);
    uint256 ltvPips = debtLWad * 1_000_000 / (collateralFloorL * WAD);

    assertEq(collateralFloorL, _readStringUint(json, ".vectors[2].expected.collateral_floor_l"));
    assertEq(ltvPips, _readStringUint(json, ".vectors[2].expected.ltv_pips"));
    assertEq(_readStringUint(json, ".vectors[3].expected.collateral_floor_l"), 0);
    assertEq(_readStringUint(json, ".vectors[3].expected.ltv_pips"), 1_000_000);
    assertEq(json.readString(".vectors[3].expected.lock_error"), "ERR_MAX_LTV");
    assertEq(_readStringUint(json, ".vectors[4].expected.ltv_pips"), 901000);
    assertEq(json.readString(".vectors[4].expected.lock_error"), "ERR_MAX_LTV");

    uint256 borrowIndexDelta = 1_000_000_000_000_000_000 * 1_000_000_000 * 60 / WAD;
    assertEq(borrowIndexDelta, _readStringUint(json, ".vectors[5].expected.delta_borrow_index_wad"));
    assertEq(
      1_000_000_000_000_000_000 + borrowIndexDelta,
      _readStringUint(json, ".vectors[5].expected.borrow_index_wad_after")
    );
    assertEq(100_000 * borrowIndexDelta, _readStringUint(json, ".vectors[5].expected.interest_accrued_wad"));
  }

  function test_ActionLifecycleFixtureSentinels() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".vectors[6].id"), "AE-LO-001");
    assertEq(json.readString(".vectors[7].id"), "AE-LO-002");
    assertEq(json.readString(".vectors[8].id"), "AE-HOOK-FEE-001");
    assertEq(json.readString(".vectors[9].id"), "AE-HOOK-REINVEST-001");
    assertEq(json.readString(".vectors[10].id"), "AE-NFT-CAP-001");

    assertEq(json.readString(".vectors[6].expected.order_status_after_cross"), "filled");
    assertEq(json.readUint(".vectors[6].expected.fill_event_index"), 1);
    assertEq(json.readUint(".vectors[6].expected.swap_event_index"), 1);
    assertEq(_readStringUint(json, ".vectors[6].expected.tick_lower_liquidity_net_after_place"), 1000);
    assertEq(_readStringInt(json, ".vectors[6].expected.tick_upper_liquidity_net_after_place"), -1000);
    assertEq(_readStringUint(json, ".vectors[6].expected.tick_lower_liquidity_net_after_fill"), 0);
    assertEq(_readStringUint(json, ".vectors[6].expected.tick_upper_liquidity_net_after_fill"), 0);
    assertEq(json.readUint(".vectors[7].expected.order_open_before_market_event_1"), 0);
    assertEq(json.readString(".vectors[7].expected.market_event_1_actor"), "arbitrage");
    assertEq(_readStringUint(json, ".vectors[8].expected.hook_fee_token0"), 1);
    assertEq(_readStringUint(json, ".vectors[8].expected.pool_input_after_hook_fee"), 9999);
    assertEq(_readStringUint(json, ".vectors[8].expected.pending_hook_fee_delta"), 1);
    assertEq(_readStringUint(json, ".vectors[9].expected.current_swap_hook_fee_token0"), 20);
    assertEq(_readStringUint(json, ".vectors[9].expected.reinvested_liquidity"), 1200);
    assertEq(_readStringUint(json, ".vectors[9].expected.pending_hook_fees0_after"), 20);
    assertEq(_readStringUint(json, ".vectors[9].expected.pending_hook_fees1_after"), 300);
    assertTrue(json.readBool(".vectors[10].expected.batch_reverted"));
    assertEq(json.readString(".vectors[10].expected.error"), "ERR_MAX_NFTS_EXCEEDED");
    assertEq(json.readUint(".vectors[10].expected.attached_nft_count_after"), 4);
    assertEq(json.readString(".vectors[12].id"), "AE-REPAIR-001");
    assertEq(_readStringUint(json, ".vectors[12].expected.repay_fraction_pips"), 134000);
    assertEq(_readStringUint(json, ".vectors[12].expected.keeper_fee_pips"), 3333);
    assertEq(_readStringUint(json, ".vectors[12].expected.principal_repaid_l"), 133196);
    assertEq(json.readString(".vectors[13].id"), "AE-PEEL-001");
    assertEq(json.readString(".vectors[13].expected.event_kind"), "peel");
    assertEq(json.readString(".vectors[13].expected.peeled_kind"), "CL");
    assertEq(_readStringUint(json, ".vectors[13].expected.peel_bounty_pips"), 100);
    assertEq(_readStringUint(json, ".vectors[13].expected.position_count_after"), 0);
    assertEq(_readStringUint(json, ".vectors[13].expected.active_liquidity_after"), 10_000_000);
    assertEq(json.readString(".vectors[14].id"), "AE-REPAIR-SWAP-001");
    assertTrue(json.readBool(".vectors[14].expected.deficit_zero_for_one"));
    assertEq(_readStringUint(json, ".vectors[14].expected.deficit_exact_out"), 33196);
    assertEq(json.readString(".vectors[14].expected.swap_token_in"), "token0");
    assertEq(_readStringUint(json, ".vectors[14].expected.swap_amount_in"), 33341);
    assertEq(_readStringUint(json, ".vectors[14].expected.swap_amount_out"), 33196);
    assertEq(json.readString(".vectors[15].id"), "AE-LO-EPOCH-001");
    assertEq(_readStringUint(json, ".vectors[15].expected.order_1_deposited0"), 3);
    assertEq(_readStringUint(json, ".vectors[15].expected.order_2_deposited0"), 6);
    assertEq(json.readUint(".vectors[15].expected.fill_count"), 2);
    assertEq(_readStringUint(json, ".vectors[15].expected.total_claimable1"), 10);
    assertEq(_readStringUint(json, ".vectors[15].expected.tick_lower_liquidity_net_after_fill"), 0);
    assertEq(_readStringUint(json, ".vectors[15].expected.tick_upper_liquidity_net_after_fill"), 0);
  }

  function _readStringUint(string memory json, string memory key) private pure returns (uint256) {
    return vm.parseUint(json.readString(key));
  }

  function _readStringInt(string memory json, string memory key) private pure returns (int256) {
    return vm.parseInt(json.readString(key));
  }
}
